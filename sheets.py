import os
import google.auth
import unicodedata
from googleapiclient.discovery import build
from ads_worker import valid_domain

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# UNICA fuente de verdad de las tiendas: pestana "Tiendas" de la Base unica (Sniper | Historicos de tiendas).
BASE_ID = os.environ.get("BASE_ID", "1cfilechpzK22smRSAz2XatjWwkNX-y70ojc1UMifE8w")

def _svc():
    creds, _ = google.auth.default(scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

def _norm_dom(d):
    d = (d or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p): d = d[len(p):]
    if d.startswith("www."): d = d[4:]
    return d.split("/")[0]

def _region_key(r):
    r = (r or "").strip().lower()
    return 0 if r.startswith("usa") else 1 if r.startswith("latam") else 2 if r.startswith("per") else 3

def ads_url(dominio):
    return ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&is_targeted_country=false"
            f"&media_type=all&q=%22{dominio}%22&search_type=keyword_exact_phrase&sort_data[direction]=desc&sort_data[mode]=total_impressions")

def read_stores(_sheet_id=None, limit=None):
    """Tienda activa = Tiendas!decision == SI y estado que NO empiece con 'Descartad'. Orden: USA/EU, LATAM, Peru; luego orden de la hoja."""
    rows = _svc().values().get(spreadsheetId=BASE_ID, range="Tiendas!A2:H").execute().get("values", [])
    out, seen = [], set()
    for i, r in enumerate(rows):
        r = r + [""] * (8 - len(r))
        dom = _norm_dom(r[0])
        if not dom or dom in seen: continue
        if r[6].strip().upper() not in ("SÍ", "SI"): continue
        if r[7].strip().lower().startswith("descartad"): continue
        seen.add(dom)
        out.append((_region_key(r[2]), i, {"tienda": r[1].strip() or dom, "dominio": dom, "url_ads_library": ads_url(dom)}))
    out.sort(key=lambda x: (x[0], x[1]))
    stores = [x[2] for x in out]
    if not stores: raise RuntimeError("Tiendas sin filas activas: no se corre (no se inventa lista)")
    return stores[:limit] if limit else stores

def _norm(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.strip().lower()) if unicodedata.category(c) != "Mn")

def parse_base_stores(rows):
    headers = {_norm(h): i for i, h in enumerate(rows[0] if rows else [])}
    if not {"dominio", "decision"}.issubset(headers):
        raise ValueError("TIENDAS_HEADER_MISSING")
    states, stores, regions = {}, {}, {}
    for row in rows[1:]:
        def cell(name):
            index = headers.get(name, len(row))
            return row[index].strip() if index < len(row) else ""
        domain = cell("dominio").lower()
        for prefix in ("https://", "http://"):
            if domain.startswith(prefix): domain = domain[len(prefix):]
        domain = domain.split("/", 1)[0].split("?", 1)[0]
        if domain.startswith("www."): domain = domain[4:]
        if not valid_domain(domain): continue
        active = _norm(cell("decision")) == "si" and not _norm(cell("estado")).startswith("descartad")
        states.setdefault(domain, []).append(active)
        stores.setdefault(domain, {"dominio": domain, "tienda": cell("tienda") or cell("nombre") or domain})
        regions.setdefault(domain, _region_key(cell("region")))
    active = [domain for domain, flags in states.items() if all(flags)]
    active.sort(key=lambda domain: regions[domain])
    return [stores[domain] for domain in active]

def read_base_stores(base_id, limit=None):
    rows = _svc().values().get(spreadsheetId=base_id, range="Tiendas!A:ZZ").execute().get("values", [])
    stores = parse_base_stores(rows)
    if not stores:
        raise RuntimeError("Tiendas sin filas activas: no se corre (no se inventa lista)")
    return stores[:limit] if limit else stores

def append_history(sheet_id, recs):
    _svc().values().append(spreadsheetId=sheet_id, range="historial!A:E", valueInputOption="USER_ENTERED",
                           body={"values": recs}).execute()

HEAD_ING = ["fecha", "dominio", "tienda", "ads_activos", "ads_activos_texto", "metodo", "leido_en", "tarjetas_cargadas"]
METODO = "ads_library_dominio_exacto_pais_ALL_activos_sin_login"

def ingesta_existing(base_id, tab):
    s = _svc()
    try:
        rows = s.values().get(spreadsheetId=base_id, range=f"{tab}!A:B").execute().get("values", [])
    except Exception:
        s.batchUpdate(spreadsheetId=base_id, body={"requests": [{"addSheet": {"properties": {"title": tab}}}]}).execute()
        s.values().update(spreadsheetId=base_id, range=f"{tab}!A1:H1", valueInputOption="RAW", body={"values": [HEAD_ING]}).execute()
        rows = []
    return {(r[0], r[1]) for r in rows if len(r) >= 2}

def append_ingesta(base_id, tab, fecha, dominio, tienda, n, leido_en, *, count_text):
    if not isinstance(count_text, str) or not count_text.strip():
        raise ValueError("MISSING_META_COUNT_TEXT")
    _svc().values().append(spreadsheetId=base_id, range=f"{tab}!A:H", valueInputOption="RAW",
                           body={"values": [[fecha, dominio, tienda, n, count_text, METODO, leido_en, ""]]}).execute()

def read_seguimiento(sheet_id, hoy):
    """Seguimiento propio de ads (no va a Mini Sniper ni a Ingesta): pestana Seguimiento_Ads del tracker, columnas dominio, tienda, desde, hasta (YYYY-MM-DD)."""
    try:
        rows = _svc().values().get(spreadsheetId=sheet_id, range="Seguimiento_Ads!A2:D").execute().get("values", [])
    except Exception:
        return []
    out = []
    for r in rows:
        r = r + [""] * (4 - len(r))
        dom = _norm_dom(r[0])
        if dom and (not r[2] or r[2] <= hoy) and (not r[3] or hoy <= r[3]):
            out.append({"tienda": r[1].strip() or dom, "dominio": dom, "url_ads_library": ads_url(dom)})
    return out
