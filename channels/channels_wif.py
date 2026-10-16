"""Private Sheets channel detector. Never logs source rows, URLs or video content."""
import datetime as dt
import json
import os
import random
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SHEET_ID = '1UBROl8RFaezkHcwmMzIygpaxIAA3k2x0zPQcpw56Ohw'
TABS = ('ECOM', 'AI APPS', 'Marca Personal')
STATE = 'BASE_CANALES_WIF'
HEADER = ['tipo', 'categoria', 'canal_url', 'channel_id', 'video_id', 'titulo', 'publicado', 'video_url', 'detectado', 'estado', 'detalle']
SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
LIMA = dt.timezone(dt.timedelta(hours=-5))

def norm(v):
    return ''.join(c for c in unicodedata.normalize('NFD', str(v).strip().lower()) if unicodedata.category(c) != 'Mn')

def public_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ChannelFeedReader/1.0)'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read(3_000_000).decode('utf-8', errors='replace')

def youtube_id(url):
    p = urllib.parse.urlsplit(url)
    if p.hostname not in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
        raise ValueError('FUENTE_NO_SOPORTADA')
    m = re.search(r'/channel/(UC[A-Za-z0-9_-]{22})(?:/|$)', p.path)
    if m:
        return m.group(1)
    if not re.fullmatch(r'/@[A-Za-z0-9_.%-]+(?:/videos|/featured|/shorts)?/?', p.path):
        raise ValueError('URL_CANAL_NO_VERIFICADA')
    text = public_get('https://www.youtube.com/' + p.path.strip('/').split('/')[0])
    for pat in (r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"', r'<meta[^>]*itemprop="channelId"[^>]*content="(UC[A-Za-z0-9_-]{22})"', r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    raise ValueError('CHANNEL_ID_NO_VERIFICABLE')

def feed(cid):
    root = ET.fromstring(public_get('https://www.youtube.com/feeds/videos.xml?channel_id=' + cid))
    ns = {'a':'http://www.w3.org/2005/Atom', 'yt':'http://www.youtube.com/xml/schemas/2015'}
    entries = []
    for e in root.findall('a:entry', ns):
        vid = e.findtext('yt:videoId', namespaces=ns) or ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            continue
        entries.append((vid, e.findtext('a:title', default='', namespaces=ns), e.findtext('a:published', default='', namespaces=ns), 'https://www.youtube.com/watch?v=' + vid))
    if not entries:
        raise ValueError('FEED_VACIO_NO_VERIFICABLE')
    return entries

def execute(request):
    for attempt in range(4):
        try:
            return request.execute()
        except Exception as ex:
            status = getattr(getattr(ex, 'resp', None), 'status', None)
            if status not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError('SHEETS_REQUEST_FAILED_' + str(status)) from None
            time.sleep(min(2 ** (attempt + 3), 64) + random.random())

def run():
    import google.auth
    from googleapiclient.discovery import build
    creds, project = google.auth.default(scopes=[SCOPE])
    svc = build('sheets', 'v4', credentials=creds, cache_discovery=False).spreadsheets()
    meta = execute(svc.get(spreadsheetId=SHEET_ID, fields='sheets(properties(sheetId,title,hidden))'))
    props = {s['properties']['title']:s['properties'] for s in meta.get('sheets', [])}
    if any(t not in props for t in TABS):
        raise RuntimeError('SOURCE_TAB_MISSING')
    if STATE not in props:
        execute(svc.batchUpdate(spreadsheetId=SHEET_ID, body={'requests':[{'addSheet':{'properties':{'title':STATE, 'hidden':True, 'gridProperties':{'rowCount':20001,'columnCount':11}}}}]}))
    ranges = ["'%s'!A1:D2000" % t for t in TABS] + ["'%s'!A1:K20001" % STATE]
    batch = execute(svc.values().batchGet(spreadsheetId=SHEET_ID, ranges=ranges)).get('valueRanges', [])
    state_values = batch[-1].get('values', [])
    if state_values and state_values[0] != HEADER:
        raise RuntimeError('STATE_SCHEMA_CONFLICT')
    if len(state_values) >= 20001:
        raise RuntimeError('STATE_CAPACITY_REACHED')
    records = [(r + ['']*11)[:11] for r in state_values[1:]]
    channels = {(r[1],r[2]):r for r in records if r[0]=='canal'}
    seen = {(r[1],r[2],r[4]) for r in records if r[0]=='video'}
    stamp = dt.datetime.now(LIMA).isoformat(timespec='seconds')
    updates = []
    counts = {'channels_ok':0, 'channels_failed':0, 'new_videos':0, 'baseline_videos':0}
    for category, data in zip(TABS, batch[:-1]):
        values = data.get('values', [])
        if not values or [norm(x) for x in values[0][:4]] != ['canal','url','activo','ultima revision']:
            raise RuntimeError('SOURCE_SCHEMA_CONFLICT')
        for rownum, cells in enumerate(values[1:], 2):
            cells = (cells + ['']*4)[:4]
            if norm(cells[2]) not in ('si','yes','true','1'):
                continue
            url = str(cells[1]).strip()
            key = (category,url)
            prior = channels.get(key)
            row = prior or ['canal',category,url,'','','','','','','','']
            initialized = bool(prior and prior[9] == 'INICIALIZADO')
            try:
                cid = row[3] or youtube_id(url)
                items = feed(cid)
                row[3], row[8], row[9], row[10] = cid, stamp, 'INICIALIZADO', ''
                for vid,title,published,link in items:
                    video_key = (category,url,vid)
                    if video_key in seen:
                        continue
                    status = 'PENDIENTE' if initialized else 'BASELINE'
                    records.append(['video',category,url,cid,vid,title,published,link,stamp,status,''])
                    seen.add(video_key)
                    counts['new_videos' if initialized else 'baseline_videos'] += 1
                updates.append({'range':"'%s'!D%d"%(category,rownum),'values':[[stamp]]})
                counts['channels_ok'] += 1
            except Exception as ex:
                # Error type only: never echo provider bodies or private row data to public logs.
                row[8], row[10] = stamp, type(ex).__name__
                counts['channels_failed'] += 1
            if not prior:
                records.append(row)
                channels[key] = row
            time.sleep(1)
    if len(records) > 20000:
        raise RuntimeError('STATE_CAPACITY_REACHED')
    updates.append({'range':"'%s'!A1:K%d"%(STATE,len(records)+1), 'values':[HEADER]+records})
    execute(svc.values().batchUpdate(spreadsheetId=SHEET_ID,body={'valueInputOption':'RAW','data':updates}))
    # One small read confirms the write path without leaking source content.
    check=execute(svc.values().get(spreadsheetId=SHEET_ID, range="'%s'!A1:K1"%STATE)).get('values',[])
    if check != [HEADER]:
        raise RuntimeError('WRITE_VERIFICATION_FAILED')
    print(json.dumps({'ok':counts['channels_failed']==0, 'project':project, **counts, 'downstream_migrated':False}))
    if counts['channels_failed']:
        raise SystemExit(2)

if __name__ == '__main__':
    run()
