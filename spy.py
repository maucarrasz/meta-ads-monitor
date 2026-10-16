# Spy personal (SEPARADO de Mini Sniper): lee cuantos anuncios activos tiene cada dominio de su propia lista.
# Lista: pestana Anunciantes del Sheet del spy (estado aprobado / seguimiento). Resultado: pestana Lecturas_Ads del mismo Sheet.
# Mismo robot (Playwright, dominio entre comillas, 240 s entre dominios, sin evasion). Nunca toca la Base unica ni Ingesta_Diaria.
import os, sys, time, datetime
from scraper import read_count
from sheets import _svc

PAUSE = 240
SHARED = {"quiz.fitme.expert"}  # plataformas compartidas: el conteo por dominio mezcla anunciantes; se lee por pagina
MAX_NONE = int(os.environ.get("MAX_NONE", "3"))
LIMA = datetime.timezone(datetime.timedelta(hours=-5))
# SPY_SHEETS = "ECOM:<id>,APPS:<id>,INFOPRODUCTOS:<id>"
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

import re
# Columnas de la pestana Anunciantes segun el tipo de Sheet: (id, dominio, nombre, link, region, pais, estado)
COLS = {"ECOM": (0, 1, 2, 3, 5, 6, 7), "APPS": (0, 8, 1, None, 9, 10, 11), "INFOPRODUCTOS": (0, 8, 1, None, 9, 10, 11)}

def activo(estado, hoy):
    e = (estado or "").strip().lower()
    if not (e.startswith("aprobad") or e.startswith("seguimiento") or e.startswith("en seguimiento")): return False
    m = re.search(r"hasta (\d{4}-\d{2}-\d{2})", e)
    return not (m and hoy > m.group(1))

def read_list(name, sid, hoy):
    c = COLS[name]
    rows = _svc().values().get(spreadsheetId=sid, range="Anunciantes!A2:U").execute().get("values", [])
    out, seen = [], set()
    for r in rows:
        r = r + [""] * (21 - len(r))
        d = norm(r[c[1]])
        urls = r[18].split() if name != "ECOM" else []
        if not d and urls:
            m = re.search(r"view_all_page_id=(\d+)", urls[0])
            if m: d = "pagina:" + m.group(1)
        if not d or d in seen or not activo(r[c[6]], hoy): continue
        seen.add(d)
        out.append({"store_id": r[c[0]], "dominio": d, "anunciante": r[c[2]], "link": r[c[3]] if c[3] is not None else "", "region": r[c[4]], "pais": r[c[5]], "anunc_url": urls, "destino": r[19].strip(), "compartido": (r[20].strip().upper() == "SI" or d in SHARED) and bool(urls)})
    return out

_YL = {}
def ya_leidos(sid, hoy, ttl=300, fresh=False):
    """Cache por corrida (5 min) para no releer Lecturas_Ads por cada dominio; fresh=True fuerza lectura (antes de escribir)."""
    t = time.time(); c = _YL.get((sid, hoy))
    if c and not fresh and t - c[0] < ttl: return c[1]
    rows = _svc().values().get(spreadsheetId=sid, range="Lecturas_Ads!A:B").execute().get("values", [])
    v = {r[1] for r in rows if len(r) > 1 and r[0] == hoy}
    _YL[(sid, hoy)] = (t, v)
    return v


def hist_ceros(sid):
    """{dominio: {fecha: total}} usando solo lecturas por dominio."""
    rows = _svc().values().get(spreadsheetId=sid, range="Lecturas_Ads!A:H").execute().get("values", [])
    h = {}
    for r in rows[1:]:
        if len(r) > 7 and r[7] in ("dominio", "anunciante") and r[6].strip().lstrip("-").isdigit():
            h.setdefault(r[1], {})[r[0]] = int(r[6])
    return h

def nota_ceros(hist, dom, hoy, res):
    if res != 0: return "Cron spy personal"
    d = datetime.date.fromisoformat(hoy); n = 1
    while True:
        d -= datetime.timedelta(days=1)
        if hist.get(dom, {}).get(d.isoformat()) == 0: n += 1
        else: break
    if n >= 5: return f"Cron spy personal | APAGADO confirmado ({n} dias seguidos sin anuncios)"
    return f"Cron spy personal | sin anuncios hoy (dia {n} de 5)"

hoy = datetime.datetime.now(LIMA).date().isoformat()
plan = []
for name, sid in SHEETS:
    if ONLY and name != ONLY: continue
    lst = read_list(name, sid, hoy)
    hechos = ya_leidos(sid, hoy)
    for s in lst:
        if s["dominio"] not in hechos: plan.append((name, sid, s))
    print(f"{name}: {len(lst)} dominios en lista, {len(lst) - sum(1 for p in plan if p[0] == name)} ya leidos hoy", flush=True)
if not plan: print("Nada pendiente hoy."); sys.exit(0)
print("Se leen:", [p[2]["dominio"] for p in plan], flush=True)
if os.environ.get("SOLO_LISTA"): sys.exit(0)
nones, login = 0, False
HIST = {sid: hist_ceros(sid) for _, sid in SHEETS}
for i, (name, sid, s) in enumerate(plan):
    if i: time.sleep(PAUSE)
    try:
        if s["dominio"] in ya_leidos(sid, hoy): print("ya leido hoy por otro run, salto", s["dominio"], flush=True); continue
    except Exception: pass
    solo_pagina = s["dominio"].startswith("pagina:") or s["compartido"]
    if solo_pagina:
        res, est = 0, "OK"
    else:
        res, est = read_count(ads_url(s["dominio"]), use_state=False)
    print([hoy, name, s["dominio"], res, est], flush=True)
    if est == "LOGIN_REQUIRED": login = True; break
    metodo, fuente, extra = "dominio", ads_url(s["dominio"]), ""
    if res == 0 and s["anunc_url"]:
        # Solo APPS/INFOPRODUCTOS: dominio dio 0 -> se lee por ANUNCIANTE (pagina) y se usa ese conteo.
        tot, partes, falla = 0, [], False
        motivo = "dominio compartido, no confiable" if s["compartido"] else ("solo anunciante" if solo_pagina else "dominio dio 0")
        for k, u in enumerate(s["anunc_url"]):
            if k or not solo_pagina: time.sleep(PAUSE)
            res2, est2 = read_count(u, use_state=False)
            print([hoy, name, s["dominio"], "anunciante", u[-20:], res2, est2], flush=True)
            if est2 == "LOGIN_REQUIRED": login = True; break
            if isinstance(res2, int): tot += res2; partes.append(res2)
            else: falla = True
        if login: break
        if falla: nones += 1; continue
        res, metodo, fuente, extra = tot, "anunciante", " ".join(s["anunc_url"]), f" | metodo anunciante ({motivo}; paginas: {'+'.join(map(str, partes))})"
    if isinstance(res, int):
        try:
            if s["dominio"] in ya_leidos(sid, hoy, fresh=True): print("duplicado evitado", s["dominio"], flush=True); continue
        except Exception: pass
        row = [hoy, s["dominio"], s["anunciante"], s["link"], s["region"], s["pais"], res, metodo, fuente,
               nota_ceros(HIST[sid], s["dominio"], hoy, res) + extra + (f" | destino: {s['destino']}" if s["destino"] else ""), s["store_id"], f"{s['store_id']}|dominio"]
        _svc().values().append(spreadsheetId=sid, range="Lecturas_Ads!A:L", valueInputOption="USER_ENTERED", body={"values": [row]}).execute()
    else:
        nones += 1
if login:
    print("ALERTA: Facebook pide login. Se detuvo, sin reintentos."); sys.exit(2)
if nones > MAX_NONE:
    print(f"ALERTA: {nones} dominios sin dato (NONE)."); sys.exit(3)
