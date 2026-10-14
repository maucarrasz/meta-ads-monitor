# Corrida diaria: lee tiendas activo=SI en el orden de la hoja (USA/EU, LATAM, Peru), 240 s entre tiendas.
# Guarda cada resultado apenas lo lee. Sale con error (-> email de GitHub) si Facebook pide login o hay muchos NONE.
import os, sys, time, datetime
from scraper import read_count
from sheets import read_stores, append_history, ingesta_existing, append_ingesta

SHEET_ID = os.environ["SHEET_ID"]
LIMIT = int(os.environ.get("MAX_STORES", "55"))
PAUSE = 240
MAX_NONE = int(os.environ.get("MAX_NONE", "5"))
BASE_ID = os.environ.get("BASE_ID", "1cfilechpzK22smRSAz2XatjWwkNX-y70ojc1UMifE8w")
ING_TAB = os.environ.get("INGESTA_TAB", "Ingesta_Diaria")
LIMA = datetime.timezone(datetime.timedelta(hours=-5))
try:
    ya = ingesta_existing(BASE_ID, ING_TAB)
except Exception as e:
    print("AVISO: no pude leer Ingesta:", str(e)[:100], flush=True); ya = set()

stores = read_stores(SHEET_ID, LIMIT)
nones, login = 0, False
for i, s in enumerate(stores):
    if i: time.sleep(PAUSE)
    res, est = read_count(s["url_ads_library"], use_state=False)
    rec = [datetime.datetime.now(LIMA).date().isoformat(), s["tienda"], s["dominio"], res, est]
    print(rec, flush=True)
    append_history(SHEET_ID, [rec])
    if isinstance(res, int) and (rec[0], s["dominio"]) not in ya:
        try:
            append_ingesta(BASE_ID, ING_TAB, rec[0], s["dominio"], s["tienda"], res, datetime.datetime.now(LIMA).isoformat(timespec="seconds"))
        except Exception as e:
            print("AVISO: no pude escribir en Ingesta:", str(e)[:100], flush=True)
    if est == "LOGIN_REQUIRED": login = True; break
    if res == "NONE": nones += 1
if login:
    print("ALERTA: Facebook pide login. Se detuvo la corrida."); sys.exit(2)
if nones > MAX_NONE:
    print(f"ALERTA: {nones} tiendas sin dato (NONE)."); sys.exit(3)
