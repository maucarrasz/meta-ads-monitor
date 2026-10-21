import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('snapshot',Path(__file__).with_name('sheets_snapshot.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Response:
 def __init__(self,status):self.status_code=status
 def json(self):return {'valueRanges':[]}
def test_one_batch_many_ranges():
 calls=[]
 def fetch(*a,**k):calls.append(k);return Response(200)
 assert m.read('secret','x'*30,['A1:B3','C1:D4'],fetch=fetch)=={'valueRanges':[]}
 assert len(calls)==1 and len([x for x in calls[0]['params'] if x[0]=='ranges'])==2
 assert calls[0]['allow_redirects'] is False
def test_quota_backoff():
 responses=iter([429,429,200]);wait=[]
 assert m.read('secret','x'*30,['A1'],fetch=lambda *a,**k:Response(next(responses)),sleep=wait.append)
 assert len(wait)==2 and all(60<=n<=65 for n in wait)
def test_permission_no_retry():
 with pytest.raises(RuntimeError,match='SHEETS_HTTP_403'):m.read('secret','x'*30,['A1'],fetch=lambda *a,**k:Response(403),sleep=lambda n:pytest.fail())
def test_retry_bounded():
 wait=[]
 with pytest.raises(RuntimeError,match='SHEETS_HTTP_429'):m.read('secret','x'*30,['A1'],fetch=lambda *a,**k:Response(429),sleep=wait.append)
 assert len(wait)==5
