import requests,re,sys,time
from bs4 import BeautifulSoup
from urllib.parse import urlsplit,urljoin,unquote
UA='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
S=requests.Session(); S.trust_env=False
def get(u): 
    r=S.get(u,headers={'User-Agent':UA},timeout=30); r.raise_for_status(); return r.text
def page_handles(html,origin,expected):
    soup=BeautifulSoup(html,'html.parser')
    for t in soup(['script','style','noscript','header','footer','nav','template']): t.decompose()
    out=[]
    for a in soup.select('a[href*="/products/"]'):
        t=urlsplit(urljoin(origin+'/',a['href']))
        if t.netloc.replace('www.','')!=urlsplit(origin).netloc.replace('www.',''): continue
        h=unquote(t.path.rstrip('/').rsplit('/products/',1)[-1])
        if h in expected and h not in out: out.append(h)
    return out
def order(origin,sort,expected,maxp=160):
    seen=[]; 
    for p in range(1,maxp+1):
        hs=page_handles(get(f'{origin}/collections/all?sort_by={sort}&page={p}'),origin,expected)
        new=[h for h in hs if h not in seen]
        if not new: break
        seen+=new
        if len(seen)>=len(expected): break
        time.sleep(.3)
    return seen
def catalog(origin):
    prods=[]
    for p in range(1,40):
        j=S.get(f'{origin}/products.json?limit=250&page={p}',headers={'User-Agent':UA},timeout=30).json()['products']
        prods+=j
        if len(j)<250: break
    return prods
def check(origin):
    prods=catalog(origin); exp={p['handle'] for p in prods}
    by={p['handle']:p for p in prods}
    cd=order(origin,'created-descending',exp); bs=order(origin,'best-selling',exp)
    res={'n':len(exp),'cd':len(cd),'bs':len(bs),'diff':cd!=bs}
    for key in('created_at','published_at'):
        v=[by[h][key] for h in cd]
        ok=sum(1 for a,b in zip(v,v[1:]) if a>=b)/max(1,len(v)-1)
        res[key]=round(ok,3)
    return res
if __name__=='__main__':
    for d in sys.argv[1:]:
        o=d if d.startswith('http') else 'https://'+d
        try: print(d,check(o.rstrip('/')),flush=True)
        except Exception as e: print(d,'ERR',repr(e)[:100],flush=True)
