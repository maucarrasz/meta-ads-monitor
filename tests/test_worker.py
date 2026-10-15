import hashlib
import hmac
import http.client
import importlib
import json
import threading
import uuid

import pytest


@pytest.fixture
def worker():
    return importlib.import_module("ads_worker")


def request(worker, *, body=None, timestamp="1700000000", signature=None,
            secret="test-secret", headers=None, path="/read", method="POST"):
    calls = []
    body = body if body is not None else json.dumps({"job_id": str(uuid.uuid4()), "domain": "example.com"}).encode()
    signature = signature if signature is not None else hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    server = worker.WorkerServer(("127.0.0.1", 0), secret=secret,
                                 reader=lambda domain: calls.append(domain) or {"status": "ready", "value": 42},
                                 now=lambda: 1700000000)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    conn = http.client.HTTPConnection(*server.server_address, timeout=3)
    values = {"Content-Type": "application/json", "X-Sniper-Timestamp": timestamp, "X-Sniper-Signature": signature}
    values.update(headers or {})
    try:
        conn.request(method, path, body, values)
        response = conn.getresponse()
        result = response.status, json.loads(response.read()), calls
    finally:
        conn.close()
        thread.join(timeout=3)
        server.server_close()
    return result


def test_signed_raw_body_reads_domain(worker):
    status, result, calls = request(worker)
    assert status == 200
    assert result["value"] == 42
    assert calls == ["example.com"]


@pytest.mark.parametrize("change", [
    {"signature": "0" * 64}, {"timestamp": "1699999939"},
    {"timestamp": "1700000061"}, {"timestamp": "not-a-number"},
    {"secret": ""}, {"headers": {"X-Sniper-Timestamp": ""}},
])
def test_bad_auth_never_opens_browser(worker, change):
    status, _, calls = request(worker, **change)
    assert status in (401, 503)
    assert calls == []


def test_signature_covers_exact_raw_body(worker):
    body = b'{"job_id":"7cce71d0-d613-4ff9-ae7a-d628edb184da","domain":"example.com"}'
    signature = hmac.new(b"test-secret", b"1700000000." + body, hashlib.sha256).hexdigest()
    status, _, calls = request(worker, body=body + b" ", signature=signature)
    assert status == 401
    assert calls == []


@pytest.mark.parametrize("domain", ["https://example.com", "example.com/x", "localhost", "127.0.0.1", "x.com?x=a", "EXAMPLE.com", "www.example.com", "tiendá.com", "example.com:443", "-bad.com"])
def test_invalid_domains_rejected_before_browser(worker, domain):
    status, _, calls = request(worker, body=json.dumps({"job_id": str(uuid.uuid4()), "domain": domain}).encode())
    assert status == 400
    assert calls == []


@pytest.mark.parametrize("body", [b"{", b"[]", b'{}', b'{"job_id":"wrong","domain":"example.com"}', b'{"job_id":"7cce71d0-d613-4ff9-ae7a-d628edb184da","domain":"example.com","url":"https://evil.com"}'])
def test_invalid_body_rejected(worker, body):
    status, _, calls = request(worker, body=body)
    assert status == 400
    assert calls == []


def test_body_is_bounded(worker):
    status, _, calls = request(worker, body=b"x" * 2049)
    assert status == 413
    assert calls == []


def test_health_needs_no_secret(worker):
    status, result, calls = request(worker, secret="", path="/health", method="GET")
    assert status == 200
    assert result == {"status": "ok"}
    assert calls == []


def test_fixed_meta_url(worker):
    from urllib.parse import parse_qs, urlsplit
    url = urlsplit(worker.ads_url("example.com"))
    assert (url.scheme, url.netloc, url.path) == ("https", "www.facebook.com", "/ads/library/")
    values = parse_qs(url.query)
    assert values["q"] == ['"example.com"']
    assert values["active_status"] == ["active"]
    assert values["country"] == ["ALL"]
    assert values["search_type"] == ["keyword_exact_phrase"]


def test_observation_hashes_actual_evidence(worker):
    payload = worker.observation("example.com", 42, "OK", {"text": "~42 results\nActual Meta text", "is_estimate": True})
    assert payload["value"] == 42
    assert payload["evidence_sha256"] == hashlib.sha256(b"~42 results\nActual Meta text").hexdigest()
    assert payload["source"] == "META_AD_LIBRARY"
    assert payload["method"] == "meta_domain_total_v1"
    assert payload["is_estimate"] is True
    assert payload["status"] == "ready"
    assert payload["error_code"] is None


@pytest.mark.parametrize("value,state", [("NONE", "NONE"), ("LOGIN_REQUIRED", "LOGIN_REQUIRED"), ("NONE", "ERROR:TimeoutError")])
def test_failed_read_never_becomes_zero(worker, value, state):
    payload = worker.observation("example.com", value, state, {})
    assert payload["value"] is None
    assert payload["status"] == "error"
    assert payload["error_code"]
    assert payload["evidence_sha256"] is None


def test_real_zero_stays_ready(worker):
    payload = worker.observation("example.com", 0, "OK", {"text": "0 results", "count_text": "0 results"})
    assert payload["status"] == "ready"
    assert payload["value"] == 0


def test_query_no_matches_is_not_verified_zero(worker):
    payload = worker.observation('example.com', 0, 'OK', {'text': 'No ads match your search criteria', 'count_text': 'No ads match your search criteria'})
    assert payload['status'] == 'error'
    assert payload['value'] is None


def test_browser_process_group_is_killed_on_timeout(worker, monkeypatch):
    import os
    import signal
    import subprocess
    import sys
    real_popen = subprocess.Popen
    children = []

    def sleeping_reader(*args, **kwargs):
        process = real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(worker.subprocess, "Popen", sleeping_reader)
    monkeypatch.setattr(worker, "READ_TIMEOUT", 0.05)
    payload = worker.read_domain("example.com")
    assert payload["status"] == "error"
    assert payload["error_code"] == "READ_TIMEOUT"
    assert payload["value"] is None
    assert children[0].returncode == -signal.SIGKILL
    with pytest.raises(ProcessLookupError):
        os.kill(children[0].pid, 0)


def test_interrupted_daily_read_cleans_up_chromium(worker, monkeypatch):
    import os
    import signal
    import subprocess
    import sys
    real_popen = subprocess.Popen
    children = []

    class Deadline(BaseException):
        pass

    def interrupted_reader(*args, **kwargs):
        process = real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(process)
        communicate = process.communicate

        def interrupt_once(*args, **kwargs):
            process.communicate = communicate
            raise Deadline()

        process.communicate = interrupt_once
        return process

    monkeypatch.setattr(worker.subprocess, "Popen", interrupted_reader)
    try:
        with pytest.raises(Deadline):
            worker.read_domain("example.com")
        assert children[0].poll() == -signal.SIGKILL
    finally:
        if children and children[0].poll() is None:
            os.killpg(children[0].pid, signal.SIGKILL)
            children[0].communicate()


@pytest.mark.parametrize("stamp", ["1699999940", "1700000060"])
def test_skew_boundary_is_allowed(worker, stamp):
    status, _, calls = request(worker, timestamp=stamp)
    assert status == 200
    assert calls == ["example.com"]


def test_duplicated_signature_headers_are_rejected(worker):
    # Multiple signatures are ambiguous even if the first value is valid.
    calls = []
    server = worker.WorkerServer(("127.0.0.1", 0), secret="test-secret", reader=lambda domain: calls.append(domain) or {"status": "ready"}, now=lambda: 1700000000)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    conn = http.client.HTTPConnection(*server.server_address, timeout=3)
    body = json.dumps({"job_id": str(uuid.uuid4()), "domain": "example.com"}).encode()
    signature = hmac.new(b"test-secret", b"1700000000." + body, hashlib.sha256).hexdigest()
    try:
        conn.putrequest("POST", "/read")
        conn.putheader("Content-Length", str(len(body)))
        conn.putheader("X-Sniper-Timestamp", "1700000000")
        conn.putheader("X-Sniper-Signature", signature)
        conn.putheader("X-Sniper-Signature", "0" * 64)
        conn.endheaders(body)
        response = conn.getresponse()
        assert response.status == 401
        assert calls == []
        response.read()
    finally:
        conn.close()
        thread.join(timeout=3)
        server.server_close()
