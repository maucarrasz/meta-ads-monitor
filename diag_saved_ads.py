"""Diagnostico unico: lee URLs de producto en Ads Library como el lector diario y guarda evidencia. Sin login, 240 s entre lecturas."""
import os, sys, time, re
from saved_ads_reader import product_ads_url, product_observation
from playwright.sync_api import sync_playwright
import hashlib
REQ=open("diag_request.txt").read().strip()
HASH=hashlib.sha1(REQ.encode()).hexdigest()[:8]
phrases = [p.strip() for p in REQ.split(",") if p.strip()]
OUT=f"funnels/diag/{HASH}"
os.makedirs(OUT, exist_ok=True)
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, channel=os.environ.get("DIAG_CHANNEL") or None)
    pg = b.new_context(locale="en-US", viewport={"width":1280,"height":900}).new_page()
    for i, ph in enumerate(phrases):
        if i: time.sleep(240)
        from urllib.parse import urlencode
        url = product_ads_url(ph) if "/products/" in ph else "https://www.facebook.com/ads/library/?"+urlencode(dict(active_status="active",ad_type="all",country="ALL",q='"'+ph+'"',search_type="keyword_exact_phrase"))
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        snaps = []
        for t in (6000, 8000, 12000):
            pg.wait_for_timeout(t)
            txt = pg.inner_text("body", timeout=15000)
            snaps.append((t, pg.url, txt))
        pg.screenshot(path=f"{OUT}/{i}.png")
        final = snaps[-1]
        print("=== ", ph)
        print("FINAL_URL", pg.url[:300])
        for t, u, tx in snaps:
            ls = [l.strip() for l in tx.splitlines() if re.search(r"result|resultado|anuncio|ads|no ads|match", l, re.I)][:8]
            print("T+", t, "len", len(tx), "lines:", ls)
        try: print("OBS", {k: v for k, v in product_observation(ph, final[2], pg.url).items() if k in ("status","value","error_code")})
        except Exception as e: print("OBS n/a", e)
        from scraper import RESULT_TOTAL
        m = RESULT_TOTAL.search(final[2]); print("TOTAL", m.group(0) if m else None)
        print("HEAD", final[2][:500].replace("\n", " | "))
        open(f"{OUT}/{i}.txt","w").write(final[1]+"\n"+final[2][:3000])
    b.close()
