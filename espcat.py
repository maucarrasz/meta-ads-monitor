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
HOY = datetime.date.today().isoformat()
DRY = bool(os.environ.get("DRY"))
ONLY = {d.strip().lower() for d in os.environ.get("ESP_ONLY_DOMAINS", "").split(",") if d.strip()}
MAXR = int(os.environ.get("ESP_MAX_RANK_PAGES", "2"))   # paginas de 250 en best-selling para ubicar el producto
HDR_RANK = ["fecha","dominio","anunciante","producto","link_producto","rank_mas_vendidos","total_productos","precio","moneda","disponibilidad","metodo","nota"]

def rows(tab, rng):
    return _svc().values().get(spreadsheetId=ECOM, range=f"{tab}!{rng}").execute().get("values", [])

def append(tab, vals):
    if DRY:
        for v in vals: print("ROW", tab, v, flush=True)
        return
    _svc().values().append(spreadsheetId=ECOM, range=f"{tab}!A:L", valueInputOption="USER_ENTERED", body={"values": vals}).execute()

def ensure_rank_tab():
    global DRY
    if DRY: return
    try:
        _svc().batchUpdate(spreadsheetId=ECOM, body={"requests":[{"addSheet":{"properties":{"title":"Lecturas_Ranking"}}}]}).execute()
    except Exception:
        pass
    cur = rows("Lecturas_Ranking", "A1:L1")
    if not cur:
        _svc().values().update(spreadsheetId=ECOM, range="Lecturas_Ranking!A1:L1", valueInputOption="RAW", body={"values":[HDR_RANK]}).execute()

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
    ensure_rank_tab()
    if DRY:
        hechos_cat, hechos_rank = set(), set()
        src = []
        for d in ONLY:
            src.append(["", d, d, f"https://{d}/", LANDINGS.get(d, f"https://{d}/")] + [""] * 6 + ["aprobado"])
    else:
        hechos_cat = {r[1] for r in rows("Lecturas_Catálogo", "A2:B") if r and r[0] == HOY and len(r) > 1}
        hechos_rank = {r[1] for r in rows("Lecturas_Ranking", "A2:B") if r and r[0] == HOY and len(r) > 1}
        src = rows("Anunciantes", "A2:Z")
    lista = []
    for r in src:
        r = r + [""] * (26 - len(r))
        if r[7].strip().lower() != "aprobado": continue  # ECOM: estado = col H (indice 7)
        dom = _norm_dom(r[1])
        if not dom or (ONLY and dom not in ONLY): continue
        lista.append({"store_id": r[0], "dominio": dom, "anunciante": r[2], "link": r[3], "landing": r[4]})
    print(f"{len(lista)} tiendas aprobadas", flush=True)
    for i, s in enumerate(lista):
        d = s["dominio"]
        if d in hechos_cat and d in hechos_rank:
            print("ya leida hoy, salto", d, flush=True); continue
        dom_cat = d
        t = total_productos(d)
        if t is None and d.count(".") > 1:  # subdominio (join.x.com): probar el dominio raiz
            raiz = ".".join(d.split(".")[-2:])
            t = total_productos(raiz)
            if t is not None: dom_cat = raiz
        if t is None:
            if d not in hechos_cat:
                append("Lecturas_Catálogo", [[HOY, d, s["anunciante"], s["link"], "", "NO VERIFICABLE", "catalogo no legible (products.json y sitemap fallaron)", s["store_id"], "cron espcatalogo"]])
            if d not in hechos_rank:
                append("Lecturas_Ranking", [[HOY, d, s["anunciante"], "NO VERIFICABLE", s["landing"], "", "", "", "", "", "NO VERIFICABLE", "catalogo no legible; no se puede rastrear el producto"]])
            print(d, "SIN CATALOGO", flush=True); continue
        fuente, total = t
        if d not in hechos_cat:
            append("Lecturas_Catálogo", [[HOY, d, s["anunciante"], s["link"], total, f"shopify {fuente}" + (f" (leido en {dom_cat})" if dom_cat != d else ""), "", s["store_id"], "cron espcatalogo"]])
        handle, como = handle_desde_landing(s["landing"], dom_cat)
        if not handle:
            if d not in hechos_rank:
                append("Lecturas_Ranking", [[HOY, d, s["anunciante"], "NO VERIFICABLE", s["landing"], "", total, "", "", "", "NO VERIFICABLE", f"producto no resuelto ({como}); no es /products/ ni enlaza a uno"]])
            print(d, "SIN PRODUCTO", como, flush=True); continue
        best = best_selling(dom_cat)
        rank, prod = "", None
        if best:
            for n, p in enumerate(best, 1):
                if p.get("handle") == handle:
                    rank, prod = n, p; break
        try:
            pj = get_json(f"https://{dom_cat}/products/{handle}.json").get("product") if prod is None else None
        except Exception:
            pj = None
        p = prod or pj
        if p is None:
            append("Lecturas_Ranking", [[HOY, d, s["anunciante"], "NO VERIFICABLE", s["landing"], "", total, "", "", "", "NO VERIFICABLE", f"handle {handle} no existe en el catalogo"]])
            print(d, "HANDLE NO EXISTE", handle, flush=True); continue
        v = (p.get("variants") or [{}])[0]
        moneda = ""
        try: moneda = get_json(f"https://{dom_cat}/cart.js").get("currency", "")
        except Exception: pass
        metodo = "best-selling" if best else "sin ranking publico"
        nota = "" if rank != "" else ("fuera del top " + str(len(best)) if best else "la tienda no expone orden de mas vendidos; solo ficha del producto")
        append("Lecturas_Ranking", [[HOY, d, s["anunciante"], p.get("title",""), f"https://{dom_cat}/products/{handle}", rank, total,
                                     v.get("price",""), moneda, "si" if v.get("available") else "no", metodo, nota]])
        print(d, "rank", rank or "-", metodo, "|", nota, "| precio", v.get("price",""), moneda, flush=True)

main()
