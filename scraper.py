import re, sys, json, os
from playwright.sync_api import sync_playwright

STATE = os.path.join(os.path.dirname(__file__), "..", "session", "state.json")
LOGIN_MARKERS = ["log in", "confirm your identity", "checkpoint", "iniciar sesión", "confirma tu identidad"]

def read_count(url, headless=True, use_state=True):
    """Devuelve (resultado, estado). resultado = entero, 'LOGIN_REQUIRED' o 'NONE'. Nunca inventa."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        kw = {"locale": "en-US"}
        if use_state and os.path.exists(STATE):
            kw["storage_state"] = STATE
        ctx = b.new_context(**kw)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(12000)
            text = page.inner_text("body")
            url_now = page.url.lower()
        except Exception as e:
            b.close(); return "NONE", "ERROR:" + type(e).__name__
        b.close()
    low = text.lower()
    m = re.search(r"~?\s*([\d,\.]+)\s+results?", text, re.I)
    if m:
        return int(re.sub(r"[^\d]", "", m.group(1))), "OK"
    if "login" in url_now or "checkpoint" in url_now or any(k in low for k in LOGIN_MARKERS):
        return "LOGIN_REQUIRED", "LOGIN_REQUIRED"
    if re.search(r"no ads match|no results|0 results", low):
        return 0, "OK"
    return "NONE", "NONE"

if __name__ == "__main__":
    print(json.dumps(read_count(sys.argv[1])))
