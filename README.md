# meta-ads-monitor
Lee cuantos anuncios activos tiene cada tienda en Meta Ads Library y lo guarda en la hoja "historial" de Google Sheets. Corre solo en GitHub Actions a las 03:00 (Peru).
- scraper.py: lee una URL. Devuelve numero, LOGIN_REQUIRED o NONE. Nunca inventa.
- main.py: corrida diaria, 240 s entre tiendas, sin paralelizar.
- Si Facebook pide login o hay muchos NONE, la corrida falla y GitHub te manda un email.
- Secretos (Settings > Secrets): SHEET_ID, GOOGLE_SA_JSON. Variable (Settings > Variables): MAX_STORES (3, luego 10, 30, 55).
- No proxies, no CAPTCHA, un solo navegador. Nunca subir session/state.json.
