# Cron aparte: catalogo Shopify de cada tienda activo=SI. Escribe en la pestana "catalogo".
import os, time, datetime
from sheets import read_stores, _svc
from catalog import read_catalog
SHEET_ID = os.environ["SHEET_ID"]
LIMIT = int(os.environ.get("MAX_STORES", "55"))
PAUSE = int(os.environ.get("STORE_PAUSE", "20"))
hoy = datetime.date.today().isoformat()
def put(rows):
    _svc().values().append(spreadsheetId=SHEET_ID, range="catalogo!A:K", valueInputOption="USER_ENTERED", body={"values": rows}).execute()
nv = 0
H = ["fecha","tienda","dominio","tipo","rank","producto","link","precio","publicado","total_productos","estado"]
try:
    _svc().batchUpdate(spreadsheetId=SHEET_ID, body={"requests":[{"addSheet":{"properties":{"title":"catalogo"}}}]}).execute()
    _svc().values().update(spreadsheetId=SHEET_ID, range="catalogo!A1:K1", valueInputOption="RAW", body={"values":[H]}).execute()
except Exception as e: print("tab catalogo ya existe o:", str(e)[:80])
for i, s in enumerate(read_stores(SHEET_ID, LIMIT)):
    if i: time.sleep(PAUSE)
    d, t = s["dominio"], s["tienda"]
    try: c = read_catalog(d)
    except Exception as e: c = None; print("error", d, e)
    if not c:
        nv += 1
        rows = [[hoy, t, d, "", "", "", "", "", "", "", "NO VERIFICABLE"]]
    else:
        rows = []
        if c["vendidos"]:
            rows += [[hoy, t, d, "VENDIDO", n, r["producto"], r["link"], r["precio"], r["publicado"], c["total"], "OK"] for n, r in enumerate(c["vendidos"], 1)]
        else:
            rows.append([hoy, t, d, "VENDIDO", "", "", "", "", "", c["total"], "NO VERIFICABLE"])
        rows += [[hoy, t, d, "RECIENTE", n, r["producto"], r["link"], r["precio"], r["publicado"], c["total"], "OK"] for n, r in enumerate(c["recientes"], 1)]
    put(rows); print(t, d, rows[0][-1], flush=True)
print("sin catalogo:", nv)
