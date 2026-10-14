import google.auth
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _svc():
    creds, _ = google.auth.default(scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

def read_stores(sheet_id, limit=None):
    rows = _svc().values().get(spreadsheetId=sheet_id, range="Hoja 1!A2:D").execute().get("values", [])
    stores = [{"tienda": r[0], "dominio": r[1], "url_ads_library": r[2]} for r in rows if len(r) >= 4 and r[3].strip().upper() == "SI"]
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
