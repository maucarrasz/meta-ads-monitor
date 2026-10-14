# Corrida diaria: lee tiendas activo=SI en el orden de la hoja (USA/EU, LATAM, Peru), 240 s entre tiendas.
# Guarda cada resultado apenas lo lee. Sale con error (-> email de GitHub) si Facebook pide login o hay muchos NONE.
import os, sys, time, datetime
from scraper import read_count
from sheets import read_stores, append_history

SHEET_ID = os.environ["SHEET_ID"]
LIMIT = int(os.environ.get("MAX_STORES", "55"))
PAUSE = 240
MAX_NONE = int(os.environ.get("MAX_NONE", "5"))

stores = read_stores(SHEET_ID, LIMIT)
nones, login = 0, False
for i, s in enumerate(stores):
    if i: time.sleep(PAUSE)
    res, est = read_count(s["url_ads_library"], use_state=False)
    rec = [datetime.date.today().isoformat(), s["tienda"], s["dominio"], res, est]
    print(rec, flush=True)
    append_history(SHEET_ID, [rec])
    if est == "LOGIN_REQUIRED": login = True; break
    if res == "NONE": nones += 1
if login:
    print("ALERTA: Facebook pide login. Se detuvo la corrida."); sys.exit(2)
if nones > MAX_NONE:
    print(f"ALERTA: {nones} tiendas sin dato (NONE)."); sys.exit(3)
