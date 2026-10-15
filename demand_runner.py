"""Claim one private job, read Meta, and finish only the lease we own."""
import base64
import json
import os
import re
import urllib.request
import uuid

from ads_worker import observation, read_domain, valid_domain


def configuration():
    dsn = os.environ.get('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL')
    if dsn:
        from psycopg.conninfo import conninfo_to_dict
        user = conninfo_to_dict(dsn).get('user', '')
        if not re.fullmatch(r'mini_sniper_ads_executor(?:\.[a-z0-9]{20})?', user):
            raise ValueError('INVALID_EXECUTOR_ROLE')
        return None, None
    origin = os.environ.get('SUPABASE_URL', '').rstrip('/')
    anon = os.environ.get('SUPABASE_ANON_KEY', '')
    token = os.environ.get('MINI_SNIPER_ADS_RPC_TOKEN', '')
    if not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co', origin) or not token:
        raise ValueError('INVALID_RPC_CONFIGURATION')
    if any(c.isspace() for c in token + anon):
        raise ValueError('INVALID_RPC_CONFIGURATION')
    if token.startswith('sb_secret_'):
        # A dedicated gateway key carries a server-configured executor role.
        # No Bearer header: the gateway supplies its scoped JWT to PostgREST.
        return origin, {'apikey': token}
    parts = token.split('.')
    if len(parts) != 3 or not anon:
        raise ValueError('INVALID_RPC_CONFIGURATION')
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    # A preflight restriction, not signature verification; Supabase verifies the
    # signed JWT and the RPC verifies its least-privilege role server-side.
    if not isinstance(claims, dict) or claims.get('role') != 'mini_sniper_ads_executor':
        raise ValueError('INVALID_RPC_ROLE')
    return origin, {'apikey': anon, 'Authorization': 'Bearer ' + token}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def rpc(name, payload):
    if name not in {'ads_demand_claim', 'ads_demand_complete'}:
        raise ValueError('INVALID_RPC')
    origin, auth = configuration()
    if origin is None:
        import psycopg
        from psycopg.types.json import Jsonb
        work_id, lease = uuid.UUID(payload['p_work_id']), uuid.UUID(payload['p_lease'])
        if name == 'ads_demand_claim':
            query = 'SELECT public.ads_demand_claim(%s,%s,%s)'
            params = (work_id, payload['p_domain'], lease)
        else:
            query = 'SELECT public.ads_demand_complete(%s,%s,%s)'
            params = (work_id, lease, Jsonb(payload['p_result']))
        with psycopg.connect(os.environ['MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL'],
                             connect_timeout=10, sslmode='require') as connection:
            connection.execute("SET LOCAL statement_timeout = '10s'")
            connection.execute("SET LOCAL lock_timeout = '3s'")
            return connection.execute(query, params).fetchone()[0]
    request = urllib.request.Request(origin + '/rest/v1/rpc/' + name,
        data=json.dumps(payload, separators=(',', ':')).encode(), method='POST', headers={
            **auth,
            'Content-Type': 'application/json', 'Accept': 'application/json'})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=12) as response:
        if response.status != 200: raise ValueError('RPC_REJECTED')
        body = response.read(65537)
        if len(body) > 65536: raise ValueError('RPC_RESPONSE_TOO_LARGE')
        return json.loads(body)


def main():
    try:
        configuration()
        work_id = str(uuid.UUID(os.environ['INPUT_WORK_ID']))
        domain = os.environ['INPUT_DOMAIN']
        if not valid_domain(domain): raise ValueError('INVALID_DOMAIN')
        lease = str(uuid.uuid4())
        claimed = rpc('ads_demand_claim', {'p_work_id': work_id, 'p_domain': domain, 'p_lease': lease})
        if claimed is None:
            print('ADS_DEMAND_DUPLICATE')
            return 0
        if not isinstance(claimed, dict) or claimed.get('domain') != domain:
            raise ValueError('INVALID_CLAIM')
        try:
            result = read_domain(domain)
        except Exception:
            result = observation(domain, None, 'READ_ERROR', {})
        if rpc('ads_demand_complete', {'p_work_id': work_id, 'p_lease': lease, 'p_result': result}) is not True:
            raise ValueError('COMPLETION_REJECTED')
        print('ADS_DEMAND_COMPLETED')
        return 0
    except Exception:
        # No tokens, response bodies, DSNs or exception details in Actions logs.
        print('ADS_DEMAND_EXECUTION_FAILED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
