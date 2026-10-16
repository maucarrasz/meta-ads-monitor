"""Diagnostico unico: lee URLs de producto en Ads Library como el lector diario y guarda evidencia. Sin login, 240 s entre lecturas."""
import os, sys, time, re
from saved_ads_reader import product_ads_url, product_observation
from playwright.sync_api import sync_playwright
phrases = [p.strip() for p in os.environ["PHRASES"].split(",") if p.strip()]
os.makedirs("diag", exist_ok=True)
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, channel="chrome")
    pg = b.new_context(locale="en-US", viewport={"width":1280,"height":900}).new_page()
    for i, ph in enumerate(phrases):
        if i: time.sleep(240)
        url = product_ads_url(ph)
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        snaps = []
        for t in (6000, 8000, 12000):
            pg.wait_for_timeout(t)
            txt = pg.inner_text("body", timeout=15000)
            snaps.append((t, pg.url, txt))
        pg.screenshot(path=f"diag/{i}.png")
        final = snaps[-1]
        print("=== ", ph)
        print("FINAL_URL", pg.url[:300])
        for t, u, tx in snaps:
            ls = [l.strip() for l in tx.splitlines() if re.search(r"result|resultado|anuncio|ads|no ads|match", l, re.I)][:8]
            print("T+", t, "len", len(tx), "lines:", ls)
        print("OBS", {k: v for k, v in product_observation(ph, final[2], pg.url).items() if k in ("status","value","error_code")})
        print("HEAD", final[2][:500].replace("\n", " | "))
    b.close()
