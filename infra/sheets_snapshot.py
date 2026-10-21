"""Private Sheets batch reader. Session token stays in memory, never in cache/logs.
Use GH_TOKEN for the authorized repository. No Google keys or new Cloud project.
"""
import argparse, base64, hashlib, json, os, random, re, subprocess, time
from pathlib import Path
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
REPO='maucarrasz/meta-ads-monitor'
WORKFLOW='sheets-read-session.yml'

def gh(*args, data=None):
    result=subprocess.run(['gh',*args],input=None if data is None else json.dumps(data),text=True,capture_output=True,check=True)
    return result.stdout

def session():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pub=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    # Workflow run-name is unique, so concurrent callers never collect each other's session.
    request_id=os.urandom(12).hex()
    gh('api','--method','POST',f'repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches','--input','-',data={'ref':'main','inputs':{'recipient_public_key':pub,'request_id':request_id}})
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        time.sleep(8)
        runs=json.loads(gh('api',f'repos/{REPO}/actions/workflows/{WORKFLOW}/runs?event=workflow_dispatch&per_page=30'))['workflow_runs']
        own=[r for r in runs if r['display_title']=='sheets-read-'+request_id]
        if not own:continue
        run=own[0]
        if run['status']!='completed':continue
        if run['conclusion']!='success':raise RuntimeError('SESSION_WORKFLOW_FAILED')
        log=gh('run','view',str(run['id']),'--repo',REPO,'--log')
        line=next((x.split('SEALED_SESSION=',1)[1] for x in log.splitlines() if 'SEALED_SESSION={' in x),None)
        if not line:raise RuntimeError('SEALED_SESSION_MISSING')
        data=json.loads(line);dec=lambda name:base64.b64decode(data[name])
        aes=key.decrypt(dec('key'),padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
        return AESGCM(aes).decrypt(dec('nonce'),dec('blob'),None).decode()
    raise RuntimeError('SESSION_TIMEOUT')

def read(token,sid,ranges,fetch=requests.get,sleep=time.sleep):
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',sid) or not ranges or len(ranges)>100:raise ValueError('INVALID_READ')
    for attempt in range(6):
        r=fetch('https://sheets.googleapis.com/v4/spreadsheets/'+sid+'/values:batchGet',params=[('ranges',v) for v in ranges]+[('valueRenderOption','FORMATTED_VALUE')],headers={'Authorization':'Bearer '+token},timeout=(5,30),allow_redirects=False)
        if r.status_code==200:return r.json()
        if r.status_code not in (429,500,502,503,504) or attempt==5:raise RuntimeError('SHEETS_HTTP_'+str(r.status_code))
        # Minimum quota refill interval on 429; bounded jitter avoids retry waves.
        sleep((60 if r.status_code==429 else min(2**(attempt+3),64))+random.random()*5)

def main():
    p=argparse.ArgumentParser();p.add_argument('--sheet-id',required=True);p.add_argument('--range',action='append',required=True);p.add_argument('--cache-dir',default=str(Path.home()/'.cache/private-sheets'));p.add_argument('--ttl',type=int,default=300);p.add_argument('--fresh',action='store_true');a=p.parse_args()
    root=Path(a.cache_dir);root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(root,0o700)
    ident=hashlib.sha256(json.dumps([a.sheet_id,a.range]).encode()).hexdigest();path=root/(ident+'.json')
    now=time.time()
    if not a.fresh and path.exists() and now-path.stat().st_mtime<max(0,a.ttl):
        data=json.loads(path.read_text());data['cache_hit']=True
    else:
        data={'observed_at':now,'cache_hit':False,'data':read(session(),a.sheet_id,a.range)}
        tmp=path.with_suffix('.tmp');fd=os.open(tmp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:json.dump(data,out)
        os.replace(tmp,path)
    print(json.dumps(data))
if __name__=='__main__':main()
