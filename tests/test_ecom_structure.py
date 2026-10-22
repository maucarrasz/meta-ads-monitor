import unittest,sys,types,os,runpy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class Request:
 def __init__(self,d):self.d=d
 def execute(self):return self.d
class Svc:
 def values(self):return self
 def batchGet(self,**kw):
  assert kw['ranges']==['Aprobados!A2:J','Seguimiento!A2:J','Lecturas_Ads!A:L','_No_reingresar!A2:B']
  return Request({'valueRanges':[{'values':[['a','approved.example']]},{'values':[['b','follow.example']]},{'values':[['fecha','dominio']]},{'values':[['blocked.example','Blocked']]}]})
class Tests(unittest.TestCase):
 def test_book_merges_lists(self):
  ns={'__name__':'test'}
  src=(ROOT/'spy.py').read_text().split('time.sleep(0 if os.environ.get')[0]
  with patch.dict(sys.modules,{'scraper':types.SimpleNamespace(read_count=lambda *a:None),'sheets':types.SimpleNamespace(_svc=lambda:Svc())}),patch.dict(os.environ,{'SPY_SHEETS':'ECOM:fixture'}):exec(src,ns)
  rows,reads=ns['book']('1SoJZ7DUGCrNlwQ4DBuNAjnLnmE-eXfPpycbC-Gzsezc')
  self.assertEqual(len(rows),2);self.assertEqual(reads,[['fecha','dominio']])
 def test_catalog_skips_info_and_uses_both_lists(self):
  with patch.dict(sys.modules,{'sheets':types.SimpleNamespace(_svc=lambda:None,_norm_dom=lambda d:d),'catalog':types.SimpleNamespace(_prods=None,_text=None,_sitemap=None)}):ns=runpy.run_path(str(ROOT/'espcat.py'),run_name='test')
  rows=[['id','example.com','Name','https://example.com','https://example.com/products/p','','','aprobado','e-commerce'],['info','info.com','Info','','','','','aprobado','infoproducto']]
  ns=ns['main'].__globals__;ns['rows']=lambda tab,rng: rows if tab=='Aprobados' else [];ns['total_productos']=lambda d:('json',4);ns['handle_desde_landing']=lambda *a:('p','url');ns['get_json']=lambda u:{'product':{'title':'P'}};ns['best_selling']=lambda d:[{'handle':'p'}];out=[];ns['append']=lambda tab,r:out.extend(r);ns['main']();self.assertEqual(len(out),1);self.assertEqual(out[0][5:7],[1,4])
if __name__ == "__main__": unittest.main()
