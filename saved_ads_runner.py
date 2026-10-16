"""Daily queue bridge using the existing restricted executor role and two fixed RPCs."""
import os
import time
import uuid
from demand_runner import configuration
from saved_ads_reader import SavedProductReader


def saved_rpc(name,args):
    if name not in {'saved_ads_claim','saved_ads_complete'}:raise ValueError('INVALID_RPC')
    if not os.environ.get('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL'):raise ValueError('MISSING_EXECUTOR_DSN')
    configuration() # Rejects owner/service-role credentials before opening a connection.
    import psycopg
    from psycopg.types.json import Jsonb
    if name=='saved_ads_claim':
        query='SELECT public.saved_ads_claim(%s)';params=(uuid.UUID(args['p_lease']),)
    else:
        query='SELECT public.saved_ads_complete(%s,%s,%s)';params=(uuid.UUID(args['p_work_id']),uuid.UUID(args['p_lease']),Jsonb(args['p_result']))
    with psycopg.connect(os.environ['MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL'],connect_timeout=10,sslmode='require') as connection:
        connection.execute("SET LOCAL statement_timeout='10s'");connection.execute("SET LOCAL lock_timeout='3s'")
        return connection.execute(query,params).fetchone()[0]


def run_jobs(*,rpc_call=saved_rpc,reader,sleep=time.sleep,max_reads=0):
    completed=0
    while True:
        lease=str(uuid.uuid4());work=rpc_call('saved_ads_claim',dict(p_lease=lease))
        if work is None:return completed
        try:result=reader.read(work['search_phrase'])
        except Exception:result=dict(status='error',value=None,error_code='READ_ERROR')
        if rpc_call('saved_ads_complete',dict(p_work_id=work['work_id'],p_lease=lease,p_result=result)) is not True:
            raise ValueError('COMPLETION_REJECTED')
        completed+=1
        if max_reads and completed>=max_reads:return completed
        if result.get('error_code') in {'LOGIN_REQUIRED','BLOCKED'}:return completed
        # Wait after completion so actual browser navigations are always >=4 minutes apart.
        sleep(240)


def main():
    try:
        if not os.environ.get('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL'):raise ValueError('MISSING_EXECUTOR_DSN')
        configuration()
        with SavedProductReader() as reader:completed=run_jobs(reader=reader,max_reads=1 if os.environ.get('SAVED_ADS_SINGLE_READ')=='1' else 0)
        print('SAVED_ADS_COMPLETED',completed);return 0
    except Exception:
        # Never expose a private queue, DSN, response body, or cookie in Actions logs.
        print('SAVED_ADS_EXECUTION_FAILED');return 1


if __name__=='__main__':raise SystemExit(main())
