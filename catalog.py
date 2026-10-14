# Lee el catalogo PUBLICO de Shopify de cada tienda (sin login, sin proxies, ritmo suave).
# Devuelve total de productos, top 10 mas vendidos y 10 mas recientes, o NO VERIFICABLE.
import json, time, urllib.request, urllib.error
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
PAUSE_REQ = 3

def _get(url):
    time.sleep(PAUSE_REQ)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def _prods(url):
    try:
        return _get(url).get("products")
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None

def _row(dom, p):
    v = (p.get("variants") or [{}])[0]
    return {"producto": p.get("title", ""), "link": f"https://{dom}/products/{p.get('handle','')}",
            "precio": v.get("price", ""), "publicado": (p.get("published_at") or "")[:10], "id": p.get("id")}

def read_catalog(dom, max_pages=12):
    allp, page = [], 1
    while page <= max_pages:
        ps = _prods(f"https://{dom}/products.json?limit=250&page={page}")
        if ps is None:
            if page == 1: return None
            break
        allp += ps
        if len(ps) < 250: break
        page += 1
    if not allp: return None
    recent = sorted(allp, key=lambda p: p.get("published_at") or p.get("created_at") or "", reverse=True)[:10]
    best = _prods(f"https://{dom}/collections/all/products.json?sort_by=best-selling&limit=10")
    base = _prods(f"https://{dom}/collections/all/products.json?limit=10")
    vendidos = None
    if best and base and [p["id"] for p in best] != [p["id"] for p in base]:
        vendidos = best
    return {"total": len(allp) if len(allp) < 250 * max_pages else f"{len(allp)}+",
            "vendidos": [_row(dom, p) for p in vendidos] if vendidos else None,
            "recientes": [_row(dom, p) for p in recent]}
