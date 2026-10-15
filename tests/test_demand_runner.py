import base64
import importlib
import json
from pathlib import Path
import uuid

import pytest


def config(monkeypatch):
    payload = base64.urlsafe_b64encode(json.dumps({'role': 'mini_sniper_ads_executor'}).encode()).decode().rstrip('=')
    monkeypatch.setenv('SUPABASE_URL', 'https://abcdefghijklmnopqrst.supabase.co')
    monkeypatch.setenv('SUPABASE_ANON_KEY', 'fixture-anon')
    monkeypatch.setenv('MINI_SNIPER_ADS_RPC_TOKEN', 'header.' + payload + '.signature')
    monkeypatch.setenv('INPUT_WORK_ID', str(uuid.uuid4()))
    monkeypatch.setenv('INPUT_DOMAIN', 'example.com')
    monkeypatch.delenv('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL', raising=False)


def test_claim_winner_reads_then_completes_with_same_lease(monkeypatch):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    calls = []
    def rpc(name, payload):
        calls.append((name, payload))
        return {'domain': 'example.com'} if name == 'ads_demand_claim' else True
    monkeypatch.setattr(runner, 'rpc', rpc)
    result = {'status': 'ready', 'value': 42, 'evidence_sha256': 'a' * 64}
    monkeypatch.setattr(runner, 'read_domain', lambda domain: result)
    assert runner.main() == 0
    assert [name for name, _ in calls] == ['ads_demand_claim', 'ads_demand_complete']
    assert calls[0][1]['p_lease'] == calls[1][1]['p_lease']
    assert calls[1][1]['p_result'] == result
    assert calls[0][1]['p_domain'] == 'example.com'


def test_duplicate_claim_never_starts_browser_or_callback(monkeypatch):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    calls = []
    monkeypatch.setattr(runner, 'rpc', lambda name, payload: calls.append(name) or None)
    monkeypatch.setattr(runner, 'read_domain', lambda _: pytest.fail('Browser started'))
    assert runner.main() == 0
    assert calls == ['ads_demand_claim']


@pytest.mark.parametrize('change', ['bad_domain', 'bad_uuid', 'wrong_role', 'bad_url', 'admin_dsn'])
def test_invalid_input_or_privilege_never_claims(monkeypatch, change):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    if change == 'bad_domain': monkeypatch.setenv('INPUT_DOMAIN', 'https://evil.com')
    if change == 'bad_uuid': monkeypatch.setenv('INPUT_WORK_ID', 'not-a-uuid')
    if change == 'wrong_role': monkeypatch.setenv('MINI_SNIPER_ADS_RPC_TOKEN', 'header.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.signature')
    if change == 'bad_url': monkeypatch.setenv('SUPABASE_URL', 'http://localhost')
    if change == 'admin_dsn': monkeypatch.setenv('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL', 'postgresql://postgres:fixture-private@localhost/postgres')
    monkeypatch.setattr(runner, 'rpc', lambda *args: pytest.fail('No callback allowed'))
    assert runner.main() == 1


def test_failed_read_finishes_as_error_instead_of_zero(monkeypatch):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    calls = []
    def rpc(name, payload):
        calls.append(payload)
        return {'domain': 'example.com'} if name == 'ads_demand_claim' else True
    def reader(_): raise RuntimeError('fixture-private-token')
    monkeypatch.setattr(runner, 'rpc', rpc)
    monkeypatch.setattr(runner, 'read_domain', reader)
    assert runner.main() == 0
    assert calls[-1]['p_result']['status'] == 'error'
    assert calls[-1]['p_result']['value'] is None


def test_rejected_completion_fails_without_logging_response(monkeypatch, capsys):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    monkeypatch.setattr(runner, 'rpc', lambda name, payload: {'domain': 'example.com'} if name == 'ads_demand_claim' else False)
    monkeypatch.setattr(runner, 'read_domain', lambda _: {'status': 'error', 'value': None, 'error_code': 'READ_TIMEOUT'})
    assert runner.main() == 1
    assert 'signature' not in capsys.readouterr().out


def test_workflow_uses_preinstalled_chrome_and_minimal_dependencies():
    text = (Path(__file__).resolve().parents[1] / '.github/workflows/ads-demand.yml').read_text()
    assert 'workflow_dispatch:' in text and '  schedule:' not in text
    assert 'work_id:' in text and 'domain:' in text
    assert 'cache: pip' in text and 'requirements-worker.lock' in text
    assert 'timeout-minutes: 5' in text
    assert 'PLAYWRIGHT_CHROMIUM_CHANNEL: chrome' in text
    assert 'playwright install' not in text and 'id-token: write' not in text
    assert 'google-github-actions' not in text and 'requirements.txt' not in text
    assert 'MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL: ${{ secrets.MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL }}' in text
    assert 'SUPABASE_ANON_KEY:' not in text and 'MINI_SNIPER_ADS_RPC_TOKEN:' not in text


@pytest.mark.parametrize('token_kind', ['dedicated_secret', 'legacy_jwt'])
def test_rpc_uses_scoped_gateway_key_or_legacy_jwt_without_mixing_headers(monkeypatch, token_kind):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    if token_kind == 'dedicated_secret':
        monkeypatch.setenv('MINI_SNIPER_ADS_RPC_TOKEN', 'sb_secret_fixture-scoped-executor')
        monkeypatch.delenv('SUPABASE_ANON_KEY')
    calls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'true'
    class Opener:
        def open(self, request, **kwargs):
            calls.append((request, kwargs))
            return Response()
    monkeypatch.setattr(runner.urllib.request, 'build_opener', lambda *args: Opener())
    assert runner.rpc('ads_demand_complete', {'p_work_id': 'fixture'}) is True
    request, options = calls[0]
    headers = {name.lower(): value for name, value in request.header_items()}
    assert request.full_url == 'https://abcdefghijklmnopqrst.supabase.co/rest/v1/rpc/ads_demand_complete'
    assert options['timeout'] == 12
    if token_kind == 'dedicated_secret':
        assert headers['apikey'] == 'sb_secret_fixture-scoped-executor'
        assert 'authorization' not in headers
    else:
        assert headers['apikey'] == 'fixture-anon'
        assert headers['authorization'].startswith('Bearer ')


@pytest.mark.parametrize('status,body', [(201, b'true'), (200, b'not json'), (200, b'x' * 65537)])
def test_rpc_rejects_invalid_http_or_unbounded_callback_bodies(monkeypatch, status, body):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 65537
            return body
    Response.status = status
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr(runner.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(ValueError):
        runner.rpc('ads_demand_complete', {})


def test_direct_database_callbacks_use_only_fixed_functions_and_prefer_private_dsn(monkeypatch):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    monkeypatch.setenv('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL', 'postgresql://mini_sniper_ads_executor:fixture-private@localhost/postgres')
    monkeypatch.delenv('MINI_SNIPER_ADS_RPC_TOKEN')
    calls = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args=None):
            calls.append((sql, args))
            return self
        def fetchone(self): return [True]
    import psycopg
    monkeypatch.setattr(psycopg, 'connect', lambda *args, **kwargs: Connection())
    monkeypatch.setattr(runner.urllib.request, 'build_opener', lambda *args: pytest.fail('No REST callback'))
    payload = {'p_work_id': str(uuid.uuid4()), 'p_lease': str(uuid.uuid4()), 'p_result': {'status': 'error', 'value': None, 'error_code': 'READ_ERROR'}}
    assert runner.rpc('ads_demand_complete', payload) is True
    assert calls[-1][0] == 'SELECT public.ads_demand_complete(%s,%s,%s)'
    assert str(calls[-1][1][0]) == payload['p_work_id']
    assert calls[-1][1][2].obj == payload['p_result']
    assert all('SET ROLE' not in sql and 'INSERT' not in sql for sql, _ in calls)


def test_private_database_failure_does_not_leak_dsn(monkeypatch, capsys):
    runner = importlib.import_module('demand_runner')
    config(monkeypatch)
    monkeypatch.setenv('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL', 'postgresql://mini_sniper_ads_executor:fixture-private@localhost/postgres')
    import psycopg
    def fail(*args, **kwargs): raise RuntimeError('fixture-private database error')
    monkeypatch.setattr(psycopg, 'connect', fail)
    assert runner.main() == 1
    assert 'fixture-private' not in capsys.readouterr().out
