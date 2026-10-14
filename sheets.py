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
