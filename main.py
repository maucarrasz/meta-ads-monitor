# Corrida diaria: lee tiendas activo=SI, 240 s entre tiendas, guarda historial, falla (-> email de GitHub) si hay problema.
import os, sys, time, datetime
from scraper import read_count
from sheets import read_stores, append_history

SHEET_ID = os.environ["SHEET_ID"]
LIMIT = int(os.environ.get("MAX_STORES", "3"))   # escalar: 3 -> 10 -> 30 -> 55
PAUSE = 240
MAX_NONE = int(os.environ.get("MAX_NONE", "1"))

stores = read_stores(SHEET_ID, LIMIT)
recs, nones, login = [], 0, False
for i, s in enumerate(stores):
    if i: time.sleep(PAUSE)
    res, est = read_count(s["url_ads_library"], use_state=False)
    recs.append([datetime.date.today().isoformat(), s["tienda"], s["dominio"], res, est])
    print(recs[-1], flush=True)
    if est == "LOGIN_REQUIRED": login = True; break
    if res == "NONE": nones += 1
if recs: append_history(SHEET_ID, recs)
if login:
    print("ALERTA: Facebook pide login. Se detuvo la corrida."); sys.exit(2)
if nones > MAX_NONE:
    print(f"ALERTA: {nones} tiendas sin dato (NONE)."); sys.exit(3)
