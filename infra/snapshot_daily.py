import json,subprocess,time,re,pathlib,os,importlib.util,datetime,base64
import requests
SNAP=pathlib.Path('/home/sandbox/snap'); SNAP.mkdir(parents=True,exist_ok=True)
def gh_token_path():
    p=SNAP/'vault_token_path.txt'
    if not p.exists():
        v=subprocess.run(['tools','vault','write-file','--name','GitHub token monitor','--key','password','--return-channel','none','--json'],capture_output=True,text=True)
        p.write_text(json.loads(v.stdout)['path'])
    return p.read_text().strip()
if not pathlib.Path('/home/sandbox/sheets_snapshot.py').exists():
    vp=gh_token_path(); env=dict(os.environ); env['GH_TOKEN']=pathlib.Path(vp).read_text().strip()
    g=subprocess.run(['gh','api','repos/maucarrasz/meta-ads-monitor/contents/infra/sheets_snapshot.py?ref=bc5599a761cc097a73cdc8acbfdd68638e90dba1'],capture_output=True,text=True,env=env,check=True)
    pathlib.Path('/home/sandbox/sheets_snapshot.py').write_text(base64.b64decode(json.loads(g.stdout)['content']).decode())
MASTER='1UBROl8RFaezkHcwmMzIygpaxIAA3k2x0zPQcpw56Ohw'
ECOM='1slSzaJ1UV1_lRIPDsgOrAek-HnBoqzIe6jQLvtmBbNQ'
MP='1bkBATz_KjFbqseJV63rTvDiaUTMEyyoWdpbSgLnjBZw'
AI='1byluo6SaMt17YvwsXCFv95GDfcdxpvQokiCEkoarKg4'

# --- WIF privado (proyecto propio 277394231713) con respaldo nativo ---
WIF=None; TOK=None
try:
    os.environ['GH_TOKEN']=pathlib.Path(gh_token_path()).read_text().strip()
    spec=importlib.util.spec_from_file_location('wifsnap','/home/sandbox/sheets_snapshot.py')
    WIF=importlib.util.module_from_spec(spec); spec.loader.exec_module(WIF)
    TOK=WIF.session()
    print('WIF session OK (proyecto propio)',flush=True)
except Exception as e:
    print('WIF session FALLO, todo por via nativa:',repr(e),flush=True)

def call(args,inp=None):
    for i in range(8):
        z=subprocess.run(args,input=inp,capture_output=True,text=True)
        if z.returncode==0: return json.loads(z.stdout)
        if '429' in z.stderr or 'RATE_LIMIT' in z.stderr or 'rate limit cooldown' in z.stderr: time.sleep(15*(i+1)); continue
        raise RuntimeError(z.stderr)
    raise RuntimeError('retries exhausted')
def ncols(c1,c2):
    def n(c):
        x=0
        for ch in c: x=x*26+ord(ch)-64
        return x
    return n(c2)-n(c1)+1
def read_range(sid,rng):
    """Read one A1 range, chunked under the 10000-cell limit; merge values."""
    m=re.match(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)$",rng)
    tab,c1,r1,c2,r2=m.group(1),m.group(2),int(m.group(3)),m.group(4),int(m.group(5))
    width=ncols(c1,c2); per=max(1,9500//width)
    values=[]; start=r1
    while start<=r2:
        end=min(r2,start+per-1)
        sub=f"{tab}!{c1}{start}:{c2}{end}"
        r=call(['tools','google-sheets','batch-read','--spreadsheet-id',sid,'--ranges',sub,'--include','values','--json'])
        v=r['ranges'][0].get('values') or []
        if not v and start>r1: break
        values+=v
        if len(v)<(end-start+1): break
        start=end+1
    return {'range':rng,'values':values}
def read_native(sid,ranges):
    out=[]
    for i in range(0,len(ranges),8):
        chunk=ranges[i:i+8]
        small=[]
        for rng in chunk:
            m=re.match(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)$",rng)
            if m and ncols(m.group(2),m.group(4))*(int(m.group(5))-int(m.group(3))+1)>9000:
                if small:
                    r=call(['tools','google-sheets','batch-read','--spreadsheet-id',sid,'--ranges',','.join(small),'--include','values','--json']); out+=r['ranges']; small=[]
                out.append(read_range(sid,rng))
            else:
                small.append(rng)
        if small:
            r=call(['tools','google-sheets','batch-read','--spreadsheet-id',sid,'--ranges',','.join(small),'--include','values','--json']); out+=r['ranges']
    return {'valueRanges':out}
def read(sid,ranges):
    if TOK:
        try:
            return WIF.read(TOK,sid,ranges)
        except Exception as e:
            print('WIF read FALLO en',sid,repr(e),'-> nativo',flush=True)
    return read_native(sid,ranges)
def meta(sid):
    if TOK:
        try:
            r=requests.get('https://sheets.googleapis.com/v4/spreadsheets/'+sid,headers={'Authorization':'Bearer '+TOK},timeout=(5,30))
            if r.status_code==200: return r.json()
            print('WIF meta',r.status_code,'-> nativo',flush=True)
        except Exception as e:
            print('WIF meta FALLO',repr(e),'-> nativo',flush=True)
    return call(['tools','google-sheets','get-spreadsheet','--spreadsheet-id',sid,'--json'])

root=pathlib.Path('/downloads/snapshots-'+datetime.datetime.now().strftime('%d%b').lower())
for d in ['ai-apps','ecom','marca-personal']: (root/d).mkdir(parents=True,exist_ok=True)
def save(slug,name,obj):
    p=root/slug/(name+'.json'); p.write_text(json.dumps(obj,ensure_ascii=False)); print(slug,name,p.stat().st_size,flush=True)

ch=read(MASTER,["'ECOM'!A1:D1000","'AI APPS'!A1:D1000","'Marca Personal'!A1:D1000"])
a,b,c=ch['valueRanges']
wif=read(MASTER,["BASE_CANALES_WIF!A1:K20000"])
state=wif['valueRanges'][0].get('values',[]); headers=state[0]
records=[dict(zip(headers,r+['']*(len(headers)-len(r)))) for r in state[1:] if r]
active={}
for cat,vr in [('ECOM',a),('AI APPS',b),('Marca Personal',c)]:
    active[cat]={str(r[1]).strip().rstrip('/').lower() for r in vr.get('values',[])[1:] if len(r)>2 and str(r[2]).strip().upper() in ('SÍ','SI','TRUE','1')}
def enabled(r): return str(r.get('canal_url','')).strip().rstrip('/').lower() in active.get(r.get('categoria'),set())
for category,slug in [('ECOM','ecom'),('AI APPS','ai-apps'),('Marca Personal','marca-personal')]:
    save(slug,'channel-registry',{'valueRanges':[a,b,c]})
    save(slug,'detector',{'header':headers,
        'pending':[r for r in records if r.get('categoria')==category and enabled(r) and r.get('tipo')=='video' and r.get('estado')=='PENDIENTE'],
        'partial_retry':[r for r in records if r.get('categoria')==category and enabled(r) and r.get('tipo')=='video' and 'pending_transcription_ids' in r.get('detalle','')],
        'channel_status':[r for r in records if r.get('categoria')==category and enabled(r) and r.get('tipo')=='canal']})

m=meta(ECOM)
save('ecom','ecom-meta',m)
save('ecom','ecom-baseline',read(ECOM,['BASE_CANALES!A1:L1000']))
save('ecom','ecom-queue',read(ECOM,["'Cola ECOM cron'!A1:N1000"]))
cur=[(z.get('title') or z.get('properties',{}).get('title','')) for z in m['sheets']]; cur=[t for t in cur if t.startswith('Curación')]
for i,title in enumerate(cur):
    save('ecom','ecom-index-'+str(i),read(ECOM,["'%s'!A1:D2000"%title.replace("'","''"),"'%s'!H1:J2000"%title.replace("'","''")]))

save('marca-personal','marca-personal-base',read(MP,['BASE_CANALES!A1','YouTube!A1:S1500']))

save('ai-apps','ai-apps-baseline',read(AI,['BASE_CANALES!A5:I1047','Pendientes!A1:D1000']))
save('ai-apps','ai-apps-index',read(AI,["'Fichas IA'!A1:D1000","'Fichas IA'!G1:H1000","'Fichas Apps'!A1:D1000","'Fichas Apps'!G1:H1000","'VIBE CODING'!A1:D1000"]))
save('ai-apps','ai-apps-standards',read(AI,['Inicio!A1:Z80',"'Fichas IA'!A1:T4","'Fichas Apps'!A1:T4","'VIBE CODING'!A1:T4"]))
print('ALL DONE',flush=True)