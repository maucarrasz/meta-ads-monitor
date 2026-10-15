# Spy personal (SEPARADO de Mini Sniper): lee cuantos anuncios activos tiene cada dominio de su propia lista.
# Lista: pestana Anunciantes del Sheet del spy (estado aprobado / seguimiento). Resultado: pestana Lecturas_Ads del mismo Sheet.
# Mismo robot (Playwright, dominio entre comillas, 240 s entre dominios, sin evasion). Nunca toca la Base unica ni Ingesta_Diaria.
import os, sys, time, datetime
from scraper import read_count
from sheets import _svc

PAUSE = 240
MAX_NONE = int(os.environ.get("MAX_NONE", "3"))
LIMA = datetime.timezone(datetime.timedelta(hours=-5))
# SPY_SHEETS = "ECOM:<id>,APPS:<id>" (solo los que se pasan; APPS e INFOPRODUCTOS se agregan al confirmarse su lista)
SHEETS = [x.split(":", 1) for x in os.environ["SPY_SHEETS"].split(",") if ":" in x]
ONLY = os.environ.get("SPY_ONLY", "")  # opcional: ECOM / APPS

def ads_url(d):
    return ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&is_targeted_country=false"
            f"&media_type=all&q=%22{d}%22&search_type=keyword_exact_phrase&sort_data[direction]=desc&sort_data[mode]=total_impressions")

def norm(d):
    d = (d or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p): d = d[len(p):]
    if d.startswith("www."): d = d[4:]
    return d.split("/")[0]

def activo(estado):
    e = (estado or "").strip().lower()
    return e.startswith("aprobad") or e.startswith("seguimiento") or e.startswith("en seguimiento")

def read_list(sid):
    rows = _svc().values().get(spreadsheetId=sid, range="Anunciantes!A2:K").execute().get("values", [])
    out, seen = [], set()
    for r in rows:
        r = r + [""] * (11 - len(r))
        d = norm(r[1])
        if not d or d in seen or not activo(r[7]): continue
        seen.add(d)
        out.append({"store_id": r[0], "dominio": d, "anunciante": r[2], "link": r[3], "region": r[5], "pais": r[6]})
    return out

def ya_leidos(sid, hoy):
    rows = _svc().values().get(spreadsheetId=sid, range="Lecturas_Ads!A:B").execute().get("values", [])
    return {r[1] for r in rows if len(r) > 1 and r[0] == hoy}

hoy = datetime.datetime.now(LIMA).date().isoformat()
plan = []
for name, sid in SHEETS:
    if ONLY and name != ONLY: continue
    lst = read_list(sid)
    hechos = ya_leidos(sid, hoy)
    for s in lst:
        if s["dominio"] not in hechos: plan.append((name, sid, s))
    print(f"{name}: {len(lst)} dominios en lista, {len(lst) - sum(1 for p in plan if p[0] == name)} ya leidos hoy", flush=True)
if not plan: print("Nada pendiente hoy."); sys.exit(0)
print("Se leen:", [p[2]["dominio"] for p in plan], flush=True)
if os.environ.get("SOLO_LISTA"): sys.exit(0)
nones, login = 0, False
for i, (name, sid, s) in enumerate(plan):
    if i: time.sleep(PAUSE)
    res, est = read_count(ads_url(s["dominio"]), use_state=False)
    print([hoy, name, s["dominio"], res, est], flush=True)
    if est == "LOGIN_REQUIRED": login = True; break
    if isinstance(res, int):
        row = [hoy, s["dominio"], s["anunciante"], s["link"], s["region"], s["pais"], res, "dominio", ads_url(s["dominio"]),
               "Cron spy personal", s["store_id"], f"{s['store_id']}|dominio"]
        _svc().values().append(spreadsheetId=sid, range="Lecturas_Ads!A:L", valueInputOption="USER_ENTERED", body={"values": [row]}).execute()
    else:
        nones += 1
if login:
    print("ALERTA: Facebook pide login. Se detuvo, sin reintentos."); sys.exit(2)
if nones > MAX_NONE:
    print(f"ALERTA: {nones} dominios sin dato (NONE)."); sys.exit(3)
