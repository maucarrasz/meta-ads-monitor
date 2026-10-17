"""AI APPS close-out worker: reads the private queue tab, fetches transcripts/X posts
from free public web sources in rotation, writes results back. Never logs content."""
import datetime as dt
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

SHEET_ID = os.environ['AI_APPS_SHEET_ID']
TAB = 'Cola cierre 17-oct'
SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}
CHUNK = 45000
BAD_MARKERS = ('just a moment', 'captcha', 'verifying your browser', 'blocking us', 'security checkpoint', 'cf-chl', 'attention required')

INVIDIOUS = ['inv.nadeko.net','invidious.f5.si','invidious.privacyredirect.com','inv.us.projectsegfau.lt','invidious.jing.rocks','invidious.materialio.us','invidious.einfachzocken.eu','iv.datura.network','invidious.perennialte.ch','iv.nboeck.de']
PIPED = ['pipedapi.adminforge.de','pipedapi.r4fo.com','pipedapi.drgns.space','pipedapi.ducks.party','api-piped.mha.fi','pipedapi.darkness.services','pipedapi.kuroworkers.com','pipedapi.vitruvianos.dev']
NITTER = ['xcancel.com','nitter.net','nitter.poast.org','nitter.privacydev.net','nitter.1d4.us','nitter.unixfox.eu','nitter.moomoo.me','nitter.drgns.space','nitter.woodland.cafe','nitter.nostate.net','nitter.adminforge.de','nitter.spaceint.fr']

def fetch(url, timeout=25, maxbytes=4_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(maxbytes).decode('utf-8', errors='replace')

def looks_bad(t):
    low = t[:3000].lower()
    return any(m in low for m in BAD_MARKERS)

def clean_text(t):
    return re.sub(r'\s+', ' ', t).strip()

def xml_to_text(xml):
    parts = re.findall(r'<text[^>]*>(.*?)</text>', xml, re.S)
    import html as h
    return clean_text(' '.join(h.unescape(re.sub(r'<[^>]+>', '', p)) for p in parts))

def vtt_to_text(vtt):
    seen, last = [], ''
    for l in vtt.splitlines():
        l = l.strip()
        if not l or '-->' in l or l.startswith(('WEBVTT','Kind:','Language:','NOTE')): continue
        l = re.sub(r'<[^>]+>', '', l)
        if l and l != last:
            seen.append(l); last = l
    return clean_text(' '.join(seen))

def src_server_vid2(vid):
    xml = fetch('https://youtubetranscript.com/?server_vid2=' + vid)
    if 'blocking us' in xml.lower(): raise ValueError('blocked')
    t = xml_to_text(xml)
    if len(t) < 1500: raise ValueError('short:%d' % len(t))
    return t

def src_invidious(vid):
    insts = INVIDIOUS[:]; random.shuffle(insts)
    last = 'none'
    for inst in insts:
        try:
            d = json.loads(fetch('https://%s/api/v1/captions/%s' % (inst, vid)))
            caps = d.get('captions') or []
            if not caps: last = 'empty'; continue
            cap = next((c for c in caps if c.get('language_code','').startswith('en')), caps[0])
            t = vtt_to_text(fetch('https://%s%s' % (inst, cap['url'])))
            if len(t) >= 1500: return t
            last = 'short'
        except Exception as ex:
            last = type(ex).__name__
    raise ValueError('invidious:%s' % last)

def src_piped(vid):
    insts = PIPED[:]; random.shuffle(insts)
    last = 'none'
    for inst in insts:
        try:
            d = json.loads(fetch('https://%s/streams/%s' % (inst, vid)))
            subs = d.get('subtitles') or []
            if not subs: last = 'empty'; continue
            sub = next((s for s in subs if s.get('code','').startswith('en')), subs[0])
            t = vtt_to_text(fetch(sub['url']))
            if len(t) >= 1500: return t
            last = 'short'
        except Exception as ex:
            last = type(ex).__name__
    raise ValueError('piped:%s' % last)

def src_viewrank(vid):
    h = fetch('https://viewrankai.com/tools/youtube-transcript/' + vid)
    if looks_bad(h): raise ValueError('challenge')
    m = re.findall(r'<(?:p|div|span)[^>]*class="[^"]*(?:segment|line|transcript)[^"]*"[^>]*>(.*?)</(?:p|div|span)>', h, re.S)
    t = clean_text(' '.join(re.sub(r'<[^>]+>', '', x) for x in m))
    if len(t) < 1500: raise ValueError('short:%d' % len(t))
    return t

def src_chooseto(vid):
    h = fetch('https://chooseto.ai/watch/' + vid)
    if looks_bad(h): raise ValueError('challenge')
    t = clean_text(re.sub(r'<[^>]+>', ' ', h))
    if len(t) < 4000: raise ValueError('short:%d' % len(t))
    return t

VIDEO_SOURCES = [('srv_vid2', src_server_vid2), ('invidious', src_invidious), ('piped', src_piped), ('viewrank', src_viewrank), ('chooseto', src_chooseto)]

def xpost_from_html(h):
    m = re.search(r'<div class="tweet-body[^"]*"[^>]*>(.*?)</div>\s*(?:<span class="tweet-date|<div class="tweet-stats)', h, re.S)
    if not m: raise ValueError('no-tweet-body')
    body = clean_text(re.sub(r'<[^>]+>', ' ', m.group(1)))
    d = re.search(r'<span class="tweet-date[^"]*"[^>]*><a[^>]*title="([^"]+)"', h, re.S)
    date = d.group(1) if d else 'FECHA NO CONSTA'
    if len(body) < 40: raise ValueError('short')
    return date + ' UTC :: ' + body

def fetch_xpost(url):
    m = re.match(r'https://x\.com/([^/]+)/status/(\d+)', url)
    if not m: raise ValueError('bad-url')
    user, sid = m.group(1), m.group(2)
    insts = NITTER[:]; random.shuffle(insts)
    last = 'none'
    for inst in insts:
        try:
            h = fetch('https://%s/%s/status/%s' % (inst, user, sid))
            if looks_bad(h): last = 'challenge'; continue
            return xpost_from_html(h), inst
        except Exception as ex:
            last = type(ex).__name__
        time.sleep(1)
    try:
        h = fetch('https://r.jina.ai/https://x.com/%s/status/%s' % (user, sid), timeout=40)
        if not looks_bad(h) and len(h) > 300:
            dm = re.search(r'Published Time:\s*(.+)', h)
            date = dm.group(1).strip() if dm else 'FECHA NO CONSTA'
            return date + ' :: ' + clean_text(h)[:8000], 'jina'
    except Exception:
        pass
    raise ValueError('xpost:%s' % last)

def execute(request):
    for attempt in range(4):
        try:
            return request.execute()
        except Exception as ex:
            status = getattr(getattr(ex, 'resp', None), 'status', None)
            if status not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(min(2 ** (attempt + 3), 64) + random.random())

def run():
    import google.auth
    from googleapiclient.discovery import build
    creds, _ = google.auth.default(scopes=[SCOPE])
    svc = build('sheets', 'v4', credentials=creds, cache_discovery=False).spreadsheets()
    values = execute(svc.values().get(spreadsheetId=SHEET_ID, range="'%s'!A1:R60" % TAB)).get('values', [])
    header, data = values[0], values[1:]
    pend = [(i + 2, r) for i, r in enumerate(data) if (list(r) + [''] * 6)[5] == 'PENDIENTE']
    shard, nsh = int(os.environ.get('SHARD', '0')), int(os.environ.get('NSHARDS', '1'))
    mine = [(rownum, r) for n, (rownum, r) in enumerate(pend) if n % nsh == shard]
    print('pendientes=%d shard=%d/%d mios=%d' % (len(pend), shard, nsh, len(mine)))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    for rownum, r in mine:
        r = list(r) + [''] * 19
        item_id, tipo, ref = r[0], r[1], r[2]
        try:
            if tipo == 'video':
                text, fuente = None, None
                errs = []
                sources = VIDEO_SOURCES[:]; random.shuffle(sources)
                for name, fn in sources:
                    try:
                        text = fn(ref); fuente = name; break
                    except Exception as ex:
                        errs.append('%s:%s' % (name, str(ex)[:40]))
                    time.sleep(2)
                if text is None:
                    raise ValueError(' | '.join(errs)[:180])
            else:
                (text, fuente) = fetch_xpost(ref)
            chunks = [text[i:i + CHUNK] for i in range(0, min(len(text), CHUNK * 8), CHUNK)]
            chunks += [''] * (8 - len(chunks))
            intentos = (r[8] + ' ; ' if r[8] else '') + now + ' OK ' + fuente
            body = {'values': [['OK', fuente, str(len(text)), intentos[-450:], now] + chunks]}
            execute(svc.values().update(spreadsheetId=SHEET_ID, range="'%s'!F%d:R%d" % (TAB, rownum, rownum), valueInputOption='RAW', body=body))
            print('OK', item_id, fuente, len(text))
        except Exception as ex:
            intentos = (r[8] + ' ; ' if r[8] else '') + now + ' FAIL ' + str(ex)[:140]
            body = {'values': [[intentos[-450:], now]]}
            execute(svc.values().update(spreadsheetId=SHEET_ID, range="'%s'!I%d:J%d" % (TAB, rownum, rownum), valueInputOption='RAW', body=body))
            print('FAIL', item_id, str(ex)[:120])
        time.sleep(random.uniform(2, 5))

run()
