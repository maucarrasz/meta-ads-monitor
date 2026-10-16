import re, sys, json, os, time
from playwright.sync_api import sync_playwright

STATE = os.path.join(os.path.dirname(__file__), "..", "session", "state.json")
# "log in" solo NO sirve: la pagina publica de Ads Library siempre trae un boton "Log in".
LOGIN_MARKERS = ["confirm your identity", "checkpoint", "iniciar sesión para continuar", "confirma tu identidad", "you must log in", "log in to continue"]
RESULT_TOTAL = re.compile(r"(?<![\w.,])(~?)\s*(\d{1,3}(?:,\d{3})+|\d+)\s+results?\b", re.I)

def read_count(url, headless=True, use_state=True, evidence=None, timeout_ms=110000):
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
        if evidence is not None:
            evidence["count_text"] = no_matches.group(0)
        return 0, "OK"
    return "NONE", "NONE"

if __name__ == "__main__":
    print(json.dumps(read_count(sys.argv[1])))
