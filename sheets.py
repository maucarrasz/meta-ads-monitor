import google.auth
import unicodedata
from googleapiclient.discovery import build
from ads_worker import valid_domain

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _svc():
    creds, _ = google.auth.default(scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

def read_stores(sheet_id, limit=None):
    rows = _svc().values().get(spreadsheetId=sheet_id, range="Hoja 1!A2:D").execute().get("values", [])
    stores = [{"tienda": r[0], "dominio": r[1], "url_ads_library": r[2]} for r in rows if len(r) >= 4 and r[3].strip().upper() == "SI"]
    return stores[:limit] if limit else stores

def _norm(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.strip().lower()) if unicodedata.category(c) != "Mn")

def parse_base_stores(rows):
    headers = {_norm(h): i for i, h in enumerate(rows[0] if rows else [])}
    if not {"dominio", "decision"}.issubset(headers):
        raise ValueError("TIENDAS_HEADER_MISSING")
    states, stores = {}, {}
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
    return [stores[d] for d, flags in states.items() if all(flags)]

def read_base_stores(base_id, limit=None):
    rows = _svc().values().get(spreadsheetId=base_id, range="Tiendas!A:ZZ").execute().get("values", [])
    stores = parse_base_stores(rows)
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
