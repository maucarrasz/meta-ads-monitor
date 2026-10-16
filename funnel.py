"""Web funnel automatico: recorre quizzes con respuestas de PRUEBA, captura cada pantalla y se detiene ante datos personales/pago.
Filas: hoja APPS (y INFOPRODUCTOS), pestana Anunciantes. W=funnel_auto (SI), X=funnel_url, Y=funnel_resultado.
Corre solo si hay filas con W=SI y Y vacio. Nunca ingresa email, telefono, nombre ni pago."""
import os, re, sys, json, time, datetime
import google.auth
from googleapiclient.discovery import build

SHEETS = dict(s.split(":") for s in os.environ.get("FUNNEL_SHEETS", "APPS:17Twaxi9-nWjmP14Bx4HRn0EneDXvNtOALNyRACxwl8k,INFOPRODUCTOS:1xbl6jJ6XZrXi5uWETSaT26BflriZwk_x8r3X3c7gRN8").split(","))
SC = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds, _ = google.auth.default(scopes=SC)
sh = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
dr = build("drive", "v3", credentials=creds, cache_discovery=False)
FORCE = os.environ.get("FORZAR", "").strip() == "1"

def pending():
    out = []
    for name, sid in SHEETS.items():
        try:
            rows = sh.values().get(spreadsheetId=sid, range="Anunciantes!A2:Y", valueRenderOption="FORMULA").execute().get("values", [])
        except Exception as e:
            print("lectura fallo", name, e); continue
        for i, r in enumerate(rows):
            r = r + [""] * (25 - len(r))
            if str(r[22]).strip().upper() == "SI" and str(r[23]).strip().startswith("http") and (FORCE or not str(r[24]).strip()):
                m = re.search(r"folders/([\w-]+)", str(r[21]))
                out.append(dict(sheet=name, sid=sid, row=i + 2, app=str(r[0]), url=str(r[23]).strip(), folder=m.group(1) if m else ""))
    return out

def setres(p, txt):
    sh.values().update(spreadsheetId=p["sid"], range=f"Anunciantes!Y{p['row']}", valueInputOption="USER_ENTERED", body={"values": [[txt]]}).execute()

PERSONAL = re.compile(r"email|e-mail|mail|tel|phone|name|nombre|card|cvv|cvc|expir|iban|الاسم|البريد|هاتف|الهاتف|رقم الجوال", re.I)
PRICE = re.compile(r"(?:[$€£]|USD|EUR|SAR|AED|ر\.?س|د\.?إ)\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|USD|EUR|SAR|AED|ر\.?س|د\.?إ|/\s?(?:month|week|mo|wk)|شهر|أسبوع)", re.I)

def test_value(url, idx):
    u = url.lower()
    if "height" in u: return ["5", "6"][idx] if idx < 2 else "5"
    if "age" in u: return "35"
    if "target" in u or "goal-weight" in u or "desired" in u: return "140"
    if "weight" in u: return "160"
    return "30"

def walk(p, outdir):
    from playwright.sync_api import sync_playwright
    os.makedirs(outdir, exist_ok=True)
    log = dict(files=[], prices=[], end="", steps=0)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, locale="ar")
        pg = ctx.new_page()
        pg.goto(p["url"], wait_until="load", timeout=60000)
        last, n, stuck = "", 0, 0
        for _ in range(120):
            pg.wait_for_timeout(2500)
            url = pg.url.split("?")[0]
            body = ""
            try: body = pg.inner_text("body")
            except Exception: pass
            sig = url + "|" + body[:120]
            if sig != last:
                n += 1; stuck = 0; last = sig
                f = f"{n:02d}-{re.sub(r'[^a-z0-9]+','-',url.split('/')[-1].lower())[:30] or 'p'}.png"
                pg.screenshot(path=os.path.join(outdir, f)); log["files"].append(f)
                for m in PRICE.findall(body): 
                    if m not in log["prices"]: log["prices"].append(m)
                print("captura", n, url)
            else:
                stuck += 1
                if stuck >= 4: log["end"] = "sin avance en " + url; break
            # parada: pago / datos personales
            inputs = pg.query_selector_all("input:not([type=radio]):not([type=checkbox]):not([type=hidden]):not([type=number]):not([type=range]), textarea")
            vis = [i for i in inputs if i.is_visible()]
            stop = False
            for i in vis:
                attrs = " ".join((i.get_attribute(a) or "") for a in ("type", "name", "placeholder", "autocomplete", "id", "aria-label"))
                if PERSONAL.search(attrs): stop = True
            if pg.query_selector("iframe[src*=stripe], iframe[src*=paypal], [data-stripe], input[autocomplete^=cc-]") or re.search(r"checkout|payment|pay|cart", url, re.I): stop = True
            if stop:
                log["end"] = "datos personales/pago en " + url; break
            # numericos de prueba
            nums = [i for i in pg.query_selector_all("input[type=number], input[inputmode=numeric], input[inputmode=decimal]") if i.is_visible()]
            for k, i in enumerate(nums):
                try: i.fill(test_value(url, k))
                except Exception: pass
            if nums: pg.wait_for_timeout(500)
            # opcion
            clicked = False
            if not nums:
                for sel in ("[role=radio]", "input[type=radio]", "[role=checkbox]", "input[type=checkbox]", "label"):
                    els = [e for e in pg.query_selector_all(sel) if e.is_visible()]
                    if els:
                        try: els[0].click(timeout=3000); clicked = True; break
                        except Exception: pass
                if not clicked:
                    # tarjetas clickeables dentro de main (opciones sin rol)
                    pg.mouse.click(640, 302); 
                pg.wait_for_timeout(1200)
            # continuar: boton habilitado
            btns = [e for e in pg.query_selector_all("button, [role=button], a[href]") if e.is_visible() and e.is_enabled()]
            btns = [e for e in btns if (e.inner_text() or "").strip() and not re.search(r"language|menu|log ?in|الدخول", e.inner_text(), re.I)]
            if btns:
                try: btns[0].click(timeout=3000)
                except Exception: pass
        log["steps"] = n
        if not log["end"]: log["end"] = "limite de pasos"
        b.close()
    return log

def drive_up(p, outdir, files):
    ok, err = 0, ""
    if not p["folder"]: return 0, "sin carpeta"
    from googleapiclient.http import MediaFileUpload
    for f in files:
        try:
            dr.files().create(body={"name": f, "parents": [p["folder"]]}, media_body=MediaFileUpload(os.path.join(outdir, f), mimetype="image/png"), supportsAllDrives=True).execute(); ok += 1
        except Exception as e:
            err = str(e)[:120]; break
    return ok, err

if __name__ == "__main__":
    ps = pending()
    if "--check" in sys.argv:
        print("pending=" + ("true" if ps else "false"))
        if os.environ.get("GITHUB_OUTPUT"): open(os.environ["GITHUB_OUTPUT"], "a").write("pending=" + ("true" if ps else "false") + "\n")
        sys.exit(0)
    for p in ps:
        slug = re.sub(r"[^a-z0-9]+", "-", p["app"].lower()).strip("-")[:40] or f"fila{p['row']}"
        outdir = f"funnels/{slug}"
        today = datetime.date.today().isoformat()
        try:
            log = walk(p, outdir)
            ok, err = drive_up(p, outdir, log["files"])
            drive = f"Drive {ok}/{len(log['files'])}" + (f" ({err})" if err else "")
            res = f"{today}: {log['steps']} pantallas. Termino: {log['end']}. Precios vistos: {', '.join(log['prices'][:6]) or 'ninguno'}. {drive}. Fotos tambien en repo funnels/{slug}"
        except Exception as e:
            res = f"{today}: ERROR {str(e)[:150]}"
        print(res); setres(p, res)
