from urllib.parse import parse_qs,urlparse
from saved_ads_runner import run_jobs
from saved_ads_reader import product_ads_url, product_observation


def test_exact_product_scope_and_actual_header_zero():
    url=product_ads_url('example.com/products/widget')
    q=parse_qs(urlparse(url).query)
    assert q['q']==['"example.com/products/widget"'] and q['country']==['ALL'] and q['active_status']==['active'] and q['search_type']==['keyword_exact_phrase']
    result=product_observation('example.com/products/widget','0 results\nOther text',url)
    assert result['value']==0 and result['status']=='ready' and result['method']=='meta_product_url_total_v1'
    assert product_observation('example.com/products/widget','No results',url)['value'] is None


def test_login_and_missing_header_are_unknown_even_with_stale_count():
    phrase='example.com/products/widget';url=product_ads_url(phrase)
    assert product_observation(phrase,'Log in to continue\n12 results',url)['error_code']=='LOGIN_REQUIRED'
    assert product_observation(phrase,'12 results','https://www.facebook.com/login/')['value'] is None
    assert product_observation(phrase,'Loading…',url)['value'] is None
    assert product_observation(phrase,'12 results',url)['value']==12


def test_one_reader_spacing_partial_login_and_no_more_claims():
    events=[];jobs=[dict(work_id='one',search_phrase='example.com/products/one'),dict(work_id='two',search_phrase='example.com/products/two'),dict(work_id='three',search_phrase='example.com/products/three')]
    def rpc(name,args):
        events.append((name,args))
        return jobs.pop(0) if name=='saved_ads_claim' and jobs else True if name=='saved_ads_complete' else None
    class Reader:
        def read(self,phrase):
            events.append(('read',phrase));return dict(status='error',value=None,error_code='LOGIN_REQUIRED') if phrase.endswith('two') else dict(status='ready',value=4)
    assert run_jobs(rpc_call=rpc,reader=Reader(),sleep=lambda n:events.append(('sleep',n)))==2
    assert [e[1] for e in events if e[0]=='sleep']==[240]
    assert len(jobs)==1
    assert [e[1]['p_result']['value'] for e in events if e[0]=='saved_ads_complete']==[4,None]


def test_reader_error_is_persisted_without_zero_and_retry_has_no_read():
    events=[];jobs=[dict(work_id='one',search_phrase='example.com/products/one')]
    def rpc(name,args):
        if name=='saved_ads_claim':return jobs.pop() if jobs else None
        events.append(args['p_result']);return True
    class Reader:
        def read(self,phrase):raise RuntimeError('failed')
    assert run_jobs(rpc_call=rpc,reader=Reader(),sleep=lambda n:None)==1
    assert events==[dict(status='error',value=None,error_code='READ_ERROR')]
    assert run_jobs(rpc_call=rpc,reader=Reader(),sleep=lambda n:None)==0


def test_redirect_or_changed_search_scope_cannot_be_reported_as_exact_url_count():
    phrase='example.com/products/widget';url=product_ads_url(phrase)
    for current in [url.replace('country=ALL','country=PE'),url.replace('keyword_exact_phrase','keyword_unordered'),url+'&q=another',url.replace('facebook.com','evil.example')]:
        assert product_observation(phrase,'9 results',current)['value'] is None


def test_bridge_refuses_arbitrary_rpc_or_owner_dsn_before_connecting(monkeypatch):
    import pytest
    from saved_ads_runner import saved_rpc
    with pytest.raises(ValueError,match='INVALID_RPC'):saved_rpc('daily_signal_append',{})
    monkeypatch.setenv('MINI_SNIPER_ADS_EXECUTOR_DATABASE_URL','postgresql://postgres:fake@127.0.0.1/postgres')
    with pytest.raises(ValueError,match='INVALID_EXECUTOR_ROLE'):saved_rpc('saved_ads_claim',{'p_lease':'10000000-0000-4000-8000-000000000001'})

def test_bounded_validation_read_stops_after_one_persisted_result_without_extra_claim():
    events=[]
    def rpc(name,args):
        events.append(name)
        return dict(work_id='one',search_phrase='example.com/products/one') if name=='saved_ads_claim' else True
    class Reader:
        def read(self,phrase):return dict(status='ready',value=0)
    assert run_jobs(rpc_call=rpc,reader=Reader(),sleep=lambda n:events.append('sleep'),max_reads=1)==1
    assert events==['saved_ads_claim','saved_ads_complete']
