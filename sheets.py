import os
import google.auth
from googleapiclient.discovery import build

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

def append_ingesta(base_id, tab, fecha, dominio, tienda, n, leido_en):
    txt = f"~{n} result" if n == 1 else f"~{n} results"
    _svc().values().append(spreadsheetId=base_id, range=f"{tab}!A:H", valueInputOption="RAW",
                           body={"values": [[fecha, dominio, tienda, n, txt, METODO, leido_en, ""]]}).execute()

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
