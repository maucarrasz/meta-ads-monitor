import re, sys, json, os, time
from playwright.sync_api import sync_playwright

STATE = os.path.join(os.path.dirname(__file__), "..", "session", "state.json")
# "log in" solo NO sirve: la pagina publica de Ads Library siempre trae un boton "Log in".
LOGIN_MARKERS = ["confirm your identity", "checkpoint", "iniciar sesión para continuar", "confirma tu identidad", "you must log in", "log in to continue"]
RESULT_TOTAL = re.compile(r"(?<![\w.,])(~?)\s*(\d{1,3}(?:,\d{3})+|\d+)\s+results?\b", re.I)

NO_MATCH = re.compile(r"no ads match your search criteria|no ads match", re.I)


CLEAN_WAIT_S = int(os.environ.get("CLEAN_RECHECK_WAIT", "60"))


def clean_recheck(url, timeout_ms=120000):
    """Doble check de un cero: sesion NUEVA y anonima (navegador y contexto nuevos, sin cookies ni estado),
    equivalente a una pestana de incognito. Sin proxies, sin cuenta, sin evasion.
    Devuelve ('NUMBER', n, texto) | ('ZERO', 0, texto) | ('UNKNOWN', None, texto)."""
    time.sleep(CLEAN_WAIT_S)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_context(locale="en-US").new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=min(60000, timeout_ms))
            page.wait_for_timeout(15000)
            text = page.inner_text("body", timeout=60000)
            if NO_MATCH.search(text) and not RESULT_TOTAL.search(text):
                page.wait_for_timeout(20000)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(15000)
                text = page.inner_text("body", timeout=60000)
            b.close()
    except Exception:
        return "UNKNOWN", None, ""
    m = RESULT_TOTAL.search(text)
    if m:
        return "NUMBER", int(m.group(2).replace(",", "")), text[m.start():m.end()].strip()
    if NO_MATCH.search(text):
        return "ZERO", 0, NO_MATCH.search(text).group(0)
    return "UNKNOWN", None, text[:200]


def read_count(url, headless=True, use_state=True, evidence=None, timeout_ms=200000):
    """Devuelve (resultado, estado). resultado = entero, 'LOGIN_REQUIRED' o 'NONE'. Nunca inventa."""
    started = time.monotonic()
    with sync_playwright() as p:
        launch = {"headless": headless}
        if os.environ.get("PLAYWRIGHT_CHROMIUM_CHANNEL"):
            launch["channel"] = os.environ["PLAYWRIGHT_CHROMIUM_CHANNEL"]
        b = p.chromium.launch(**launch)
        kw = {"locale": "en-US"}
        if use_state and os.path.exists(STATE):
            kw["storage_state"] = STATE
        ctx = b.new_context(**kw)
        page = ctx.new_page()
        try:
            remaining = lambda: max(1, int(timeout_ms - (time.monotonic() - started) * 1000))
            page.goto(url, wait_until="domcontentloaded", timeout=min(60000, remaining()))
            page.wait_for_timeout(min(12000, remaining()))
            text = page.inner_text("body", timeout=remaining())
            url_now = page.url.lower()
            # Un "No ads match" puede ser un falso cero (la pagina aun no cargo o Facebook devolvio vacio).
            # Se confirma recargando: el cero solo vale si se repite; si aparece un numero, gana el numero.
            for _ in range(2):
                if RESULT_TOTAL.search(text) or not NO_MATCH.search(text):
                    break
                page.wait_for_timeout(20000)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(15000)
                text2 = page.inner_text("body", timeout=60000)
                url_now = page.url.lower()
                if RESULT_TOTAL.search(text2) or not NO_MATCH.search(text2):
                    text = text2
                    break
                text = text2
        except Exception as e:
            b.close(); return "NONE", "ERROR:" + type(e).__name__
        b.close()
    low = text.lower()
    if evidence is not None:
        evidence["text"] = text
    if "login" in url_now or "checkpoint" in url_now or any(k in low for k in LOGIN_MARKERS):
        return "LOGIN_REQUIRED", "LOGIN_REQUIRED"
    if any(k in low for k in ("temporarily blocked", "access denied", "unusual activity", "you’re temporarily blocked", "too many requests")):
        return "NONE", "BLOCKED"
    m = RESULT_TOTAL.search(text)
    if m:
        if evidence is not None:
            qualifier = re.search(r"(?:about|approximately)\s*$", text[:m.start()], re.I)
            evidence["is_estimate"] = bool(m.group(1)) or bool(qualifier)
            evidence["count_text"] = text[qualifier.start() if qualifier else m.start():m.end()].strip()
        return int(m.group(2).replace(",", "")), "OK"
    no_matches = re.search(r"no ads match your search criteria|no ads match|no results|0 results", text, re.I)
    if no_matches:
        # Regla fija (Mauricio 20-oct): un cero solo vale tras doble check en sesion limpia/anonima distinta.
        kind, n, ctext = clean_recheck(url)
        if kind == "NUMBER":
            if evidence is not None:
                evidence["count_text"] = ctext; evidence["is_estimate"] = ctext.startswith("~"); evidence["zero_overridden_by_clean"] = True
            return n, "OK"
        if kind == "ZERO":
            if evidence is not None:
                evidence["count_text"] = no_matches.group(0); evidence["zero_clean_confirmed"] = True
            return 0, "OK"
        return "NONE", "ZERO_UNCONFIRMED"
    # La pagina cargo pero sin conteo ni "no ads match" (cascarón vacío / render lento, p.ej. i900ma-9e 20-oct).
    # Mismo doble check en sesion limpia antes de declarar NONE, para no tumbar la corrida por un falso sin-dato.
    kind, n, ctext = clean_recheck(url)
    if kind == "NUMBER":
        if evidence is not None:
            evidence["count_text"] = ctext; evidence["is_estimate"] = ctext.startswith("~"); evidence["none_overridden_by_clean"] = True
        return n, "OK"
    if kind == "ZERO":
        if evidence is not None:
            evidence["count_text"] = "0 tras cascaron vacio"; evidence["zero_clean_confirmed"] = True
        return 0, "OK"
    return "NONE", "NONE"

if __name__ == "__main__":
    print(json.dumps(read_count(sys.argv[1])))
