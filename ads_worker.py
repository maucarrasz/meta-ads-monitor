"""Signed, bounded HTTP entry point for public Meta domain totals."""
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

MAX_BODY = 2048
READ_TIMEOUT = 330  # la ruta de cero (recarga x2 + espera 60s + doble check anonimo) necesita ~200-300s; con 110 mataba ceros reales (homezonestore 22-oct)


def valid_domain(domain):
    if not isinstance(domain, str) or len(domain) > 253 or domain != domain.lower():
        return False
    if not domain.isascii() or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", domain):
        return False
    try:
        ipaddress.ip_address(domain)
        return False
    except ValueError:
        return True


def ads_url(domain):
    if not valid_domain(domain):
        raise ValueError("INVALID_DOMAIN")
    return "https://www.facebook.com/ads/library/?" + urlencode({
        "active_status": "active", "ad_type": "all", "country": "ALL",
        "is_targeted_country": "false", "media_type": "all", "q": '"' + domain + '"',
        "search_type": "keyword_exact_phrase", "sort_data[direction]": "desc",
        "sort_data[mode]": "total_impressions",
    })


def observation(domain, value, state, evidence):
    ready = type(value) is int and value >= 0 and state == "OK"
    if ready and value == 0:
        literal = evidence.get("count_text") or evidence.get("text", "")
        ready = bool(re.fullmatch(r"~?0\s+(?:results?|anuncios?|resultados?)", literal.strip(), re.I))
    text = evidence.get("text")
    return {
        "status": "ready" if ready else "error", "value": value if ready else None,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "META_AD_LIBRARY", "method": "meta_domain_total_v1",
        "is_estimate": bool(evidence.get("is_estimate", False)),
        "evidence_url": ads_url(domain),
        "evidence_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "error_code": None if ready else (state if state in {"LOGIN_REQUIRED", "BLOCKED", "READ_TIMEOUT", "READ_ERROR"} else "NO_VERIFIABLE_COUNT"),
    }


def read_domain(domain, *, include_count_text=False):
    """An OS process boundary bounds Chromium, including its child processes."""
    command = [sys.executable, os.path.join(os.path.dirname(__file__), "read_domain.py"), domain]
    if include_count_text:
        command.append("--include-count-text")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=READ_TIMEOUT)
        if process.returncode != 0:
            return observation(domain, None, "READ_ERROR", {})
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return observation(domain, None, "READ_TIMEOUT", {})
    except (ValueError, OSError):
        return observation(domain, None, "READ_ERROR", {})
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()


class WorkerServer(HTTPServer):
    def __init__(self, address, *, secret, reader=read_domain, now=time.time):
        self.secret = secret
        self.reader = reader
        self.now = now
        super().__init__(address, WorkerHandler)


class WorkerHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # Do not log signed payloads, headers or secrets.
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def respond(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200, {"status": "ok"}) if self.path == "/health" else self.respond(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if self.path != "/read":
            return self.respond(404, {"error": "NOT_FOUND"})
        if not self.server.secret:
            return self.respond(503, {"error": "WORKER_NOT_CONFIGURED"})
        if any(len(self.headers.get_all(name, [])) != 1 for name in ("X-Sniper-Timestamp", "X-Sniper-Signature")):
            return self.respond(401, {"error": "INVALID_SIGNATURE"})
        if self.headers.get("Transfer-Encoding"):
            return self.respond(400, {"error": "INVALID_BODY"})
        if len(self.headers.get_all("Content-Length", [])) != 1:
            return self.respond(400, {"error": "INVALID_BODY"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self.respond(400, {"error": "INVALID_BODY"})
        if length > MAX_BODY:
            return self.respond(413, {"error": "BODY_TOO_LARGE"})
        if length <= 0:
            return self.respond(400, {"error": "INVALID_BODY"})
        try:
            body = self.rfile.read(length)
        except TimeoutError:
            return self.respond(408, {"error": "BODY_TIMEOUT"})
        stamp = self.headers.get("X-Sniper-Timestamp", "")
        signature = self.headers.get("X-Sniper-Signature", "")
        if not re.fullmatch(r"\d{1,12}", stamp) or abs(self.server.now() - int(stamp)) > 60:
            return self.respond(401, {"error": "INVALID_SIGNATURE"})
        expected = hmac.new(self.server.secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not re.fullmatch(r"[a-f0-9]{64}", signature) or not hmac.compare_digest(signature, expected):
            return self.respond(401, {"error": "INVALID_SIGNATURE"})
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {"job_id", "domain"}:
                raise ValueError("INVALID_BODY")
            uuid.UUID(payload["job_id"])
            if not valid_domain(payload["domain"]):
                raise ValueError("INVALID_DOMAIN")
        except (ValueError, TypeError, AttributeError):
            return self.respond(400, {"error": "INVALID_BODY"})
        try:
            result = self.server.reader(payload["domain"])
        except Exception:
            result = observation(payload["domain"], None, "READ_ERROR", {})
        return self.respond(200, result)


if __name__ == "__main__":
    WorkerServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))),
                 secret=os.environ.get("MINI_SNIPER_ADS_WORKER_SECRET", "")).serve_forever()
