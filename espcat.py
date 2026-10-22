# Catalogo + ranking del ESPIA PERSONAL ECOM (separado de Mini Sniper).
# Por cada tienda aprobada en Anunciantes: total del catalogo y, si se resuelve
# el producto de su landing, su puesto en el ranking de mas vendidos.
# Publico Shopify (products.json / sitemap), ritmo suave, sin login. Nunca inventa:
# si no se puede leer o el producto no aparece, se escribe NO VERIFICABLE con el motivo.
import os, re, json, time, datetime, urllib.request, urllib.error
from sheets import _svc, _norm_dom
from catalog import _prods, _text, _sitemap

LANDINGS = {d.strip().split("=", 1)[0]: d.strip().split("=", 1)[1] for d in os.environ.get("ESP_LANDINGS", "").split("|") if "=" in d}
ECOM = os.environ.get("ECOM_ID", "1SoJZ7DUGCrNlwQ4DBuNAjnLnmE-eXfPpycbC-Gzsezc")
HOY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).date().isoformat()
DRY = bool(os.environ.get("DRY"))
ONLY = {d.strip().lower() for d in os.environ.get("ESP_ONLY_DOMAINS", "").split(",") if d.strip()}
MAXR = int(os.environ.get("ESP_MAX_RANK_PAGES", "2"))   # paginas de 250 en best-selling para ubicar el producto
def rows(tab, rng):
    return _svc().values().get(spreadsheetId=ECOM, range=f"{tab}!{rng}").execute().get("values", [])

def append(tab, vals):
    if DRY:
        for v in vals: print("ROW", tab, v, flush=True)
        return
    _svc().values().append(spreadsheetId=ECOM, range=f"{tab}!A:I", valueInputOption="USER_ENTERED", body={"values": vals}).execute()

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15", "Accept": "application/json"})
    time.sleep(float(os.environ.get("CAT_PAUSE", "3")))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def get_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15"})
    time.sleep(float(os.environ.get("CAT_PAUSE", "3")))
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def total_productos(dom):
    n, page = 0, 1
    while page <= 12:
        ps = _prods(f"https://{dom}/products.json?limit=250&page={page}")
        if not ps: break
        n += len(ps)
        if len(ps) < 250: return ("json", n)
        page += 1
    if n == 0:
        sm = _sitemap(dom)
        return ("sitemap", len(sm)) if sm else None
    return ("json", f"{n}+")

def best_selling(dom):
    """Lista ordenada por mas vendidos (hasta MAXR paginas de 250) o None si la tienda no la expone."""
    first = _prods(f"https://{dom}/collections/all/products.json?sort_by=best-selling&limit=250")
    base = _prods(f"https://{dom}/collections/all/products.json?limit=250")
    if first is None: return None
    if base and len(first) == len(base) and [p.get("id") for p in first] == [p.get("id") for p in base]:
        return None  # el orden best-selling no difiere del base: la tienda no expone ranking real
    out = list(first)
    for page in range(2, MAXR + 1):
        if len(first) < 250: break
        ps = _prods(f"https://{dom}/collections/all/products.json?sort_by=best-selling&limit=250&page={page}")
        if not ps: break
        out += ps
    return out

def handle_desde_landing(landing, dom):
    m = re.search(r"/products/([A-Za-z0-9\-_%]+)", landing or "")
    if m: return m.group(1), "url"
    try:
        html = get_html(landing if landing.startswith("http") else f"https://{dom}/")
    except Exception:
        return None, "landing no carga"
    m = re.search(r"/products/([a-z0-9\-]+)", html)
    return (m.group(1), "html") if m else (None, "landing sin enlace a producto")

def main():
    # Daily product position plus catalog size. Non-products are not scraped.
    existing = {r[1] for r in rows("Lecturas_Catalogo", "A2:B") if len(r) > 1 and r[0] == HOY}
    source = rows("Aprobados", "A2:J") + rows("Seguimiento", "A2:J")
    for row in source:
        r = row + [""] * (10 - len(row))
        d = _norm_dom(r[1])
        if not d or d in existing or (ONLY and d not in ONLY): continue
        if "infoproduct" in r[8].lower() or "app" in r[8].lower(): continue
        if not (r[7].lower().startswith(("aprobad", "seguimiento", "en seguimiento"))): continue
        try:
            t = total_productos(d)
            dom_cat = d
            if t is None and d.count(".") > 1:
                root = ".".join(d.split(".")[-2:])
                t = total_productos(root)
                if t is not None: dom_cat = root
            total = t[1] if t else ""
            handle, reason = handle_desde_landing(r[4], dom_cat)
            title, link, rank, method, note = "", r[4], "", "NO VERIFICABLE", ""
            if handle:
                try: product = get_json(f"https://{dom_cat}/products/{handle}.json").get("product")
                except Exception: product = None
                if product:
                    title = product.get("title", "")
                    link = f"https://{dom_cat}/products/{handle}"
                    best = best_selling(dom_cat)
                    if best:
                        rank = next((i for i, p in enumerate(best, 1) if p.get("handle") == handle), "")
                        method = "best-selling" if rank != "" else "NO VERIFICABLE"
                        note = "" if rank != "" else f"producto fuera de los {len(best)} productos leidos"
                    else: note = "sin ranking publico verificable"
                else: note = "producto no resuelto en catalogo"
            else: note = reason
            if not t: note = "catalogo no legible; " + note
            append("Lecturas_Catalogo", [[HOY, d, r[2], title, link, rank, total, method, note]])
            print(d, "catalog", total, "rank", rank, method, flush=True)
        except Exception as exc:
            append("Lecturas_Catalogo", [[HOY, d, r[2], "", r[4], "", "", "NO VERIFICABLE", type(exc).__name__]])

if __name__ == "__main__": main()
