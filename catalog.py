# Lee el catalogo PUBLICO de Shopify de cada tienda (sin login, sin proxies, ritmo suave).
# Devuelve total de productos, top 10 mas vendidos y 10 mas recientes, o NO VERIFICABLE.
import json, re, time, urllib.request, urllib.error
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"  # catalogo: se pide como movil
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


def _text(url):
    time.sleep(PAUSE_REQ)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def _sitemap(dom):
    """Respaldo cuando /products.json no existe (tiendas headless). Usa el sitemap publico."""
    try:
        x = _text(f"https://{dom}/sitemap.xml")
        subs = re.findall(r"<loc>([^<]*sitemap_products[^<]*)</loc>", x)
        docs = [_text(u) for u in subs] if subs else [x]
    except Exception:
        return None
    items = []
    for d in docs:
        for blk in re.findall(r"<url>([\s\S]*?)</url>", d):
            m = re.search(r"<loc>https?://[^/<]+/products/([^<]+)</loc>", blk)
            if not m: continue
            t = re.search(r"<image:title>([^<]*)</image:title>", blk)
            lm = re.search(r"<lastmod>([^<]*)</lastmod>", blk)
            items.append({"handle": m.group(1), "title": (t.group(1) if t else m.group(1).replace("-", " ")),
                          "lastmod": lm.group(1) if lm else ""})
    return items or None

def read_catalog(dom, max_pages=12):
    allp, page = [], 1
    while page <= max_pages:
        ps = _prods(f"https://{dom}/products.json?limit=250&page={page}")
        if ps is None:
            if page == 1: break
            break
        allp += ps
        if len(ps) < 250: break
        page += 1
    if not allp:
        sm = _sitemap(dom)
        if not sm: return None
        rec = sorted(sm, key=lambda p: p["lastmod"], reverse=True)[:10]
        return {"total": len(sm), "vendidos": None, "fuente": "sitemap",
                "recientes": [{"producto": p["title"], "link": f"https://{dom}/products/{p['handle']}", "precio": "",
                               "publicado": p["lastmod"][:10], "id": None} for p in rec]}
    recent = sorted(allp, key=lambda p: p.get("published_at") or p.get("created_at") or "", reverse=True)[:10]
    best = _prods(f"https://{dom}/collections/all/products.json?sort_by=best-selling&limit=10")
    base = _prods(f"https://{dom}/collections/all/products.json?limit=10")
    vendidos = None
    if best and base and [p["id"] for p in best] != [p["id"] for p in base]:
        vendidos = best
    return {"total": len(allp) if len(allp) < 250 * max_pages else f"{len(allp)}+",
            "vendidos": [_row(dom, p) for p in vendidos] if vendidos else None,
            "recientes": [_row(dom, p) for p in recent]}
