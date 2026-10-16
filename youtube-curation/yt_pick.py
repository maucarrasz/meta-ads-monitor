import csv,json,os,re,subprocess,sys,time,datetime
shard,nsh=int(os.environ.get("SHARD","0")),int(os.environ.get("NSHARDS","1"))
rows=[r for r in csv.reader(open("youtube-curation/canales.csv"))]
rows=[r for i,r in enumerate(rows) if i%nsh==shard]
if os.environ.get("ONLY"): rows=[r for r in rows if r[0] in os.environ["ONLY"].split(",")]
out="youtube-curation/out"; os.makedirs(out,exist_ok=True)
cut=(datetime.date.today()-datetime.timedelta(days=365)).strftime("%Y%m%d")
def run(a,t=120):
    return subprocess.run(a,capture_output=True,text=True,timeout=t)
def vtt_text(p):
    seen=[];last=""
    for l in open(p,encoding="utf8"):
        l=l.strip()
        if not l or "-->" in l or l.startswith(("WEBVTT","Kind:","Language:")): continue
        l=re.sub(r"<[^>]+>","",l)
        if l and l!=last: seen.append(l); last=l
    return " ".join(seen)
for n,name,handle,url in rows:
    res={"n":n,"canal":name,"handle":handle,"url":url,"videos":[],"estado":""}
    try:
        p=run(["yt-dlp","--flat-playlist","--playlist-end","40","-J",url.rstrip("/")+"/videos"])
        if p.returncode: res["estado"]="NO VERIFICABLE: lista bloqueada/error: "+p.stderr[-200:]; json.dump(res,open(f"{out}/{n}.json","w"),ensure_ascii=False,indent=1); continue
        ents=json.loads(p.stdout).get("entries",[])
        ents=[e for e in ents if e and e.get("id")]
        ents.sort(key=lambda e:-(e.get("view_count") or 0))
        for e in ents[:6]:
            if len(res["videos"])>=3: break
            vid=e["id"]
            def get(langs):
                return run(["yt-dlp","--skip-download","--no-simulate","--write-auto-subs","--write-subs","--sub-langs",langs,"--sub-format","vtt","-o",f"/tmp/{vid}","--print","%(upload_date)s|%(view_count)s|%(duration)s|%(title)s","https://www.youtube.com/watch?v="+vid])
            import glob
            m=get("en-orig,en")
            if not glob.glob(f"/tmp/{vid}*.vtt"): m2=get("es-orig,es"); m=m2 if m2.stdout.strip() else m
            if "429" in m.stderr: res["rate_limit_429"]=True; time.sleep(60)
            meta=(m.stdout.strip().splitlines() or [""])[0].split("|",3)
            if len(meta)<4: res["videos"].append({"id":vid,"estado":"NO VERIFICABLE: "+m.stderr[-150:]});continue
            if meta[0]<cut and meta[0].isdigit(): continue
            v={"id":vid,"link":"https://www.youtube.com/watch?v="+vid,"fecha":meta[0],"vistas":meta[1],"duracion_s":meta[2],"titulo":meta[3]}
            import glob
            fs=glob.glob(f"/tmp/{vid}*.vtt")
            if fs:
                t=vtt_text(fs[0]); open(f"{out}/{n}_{vid}.txt","w",encoding="utf8").write(t); v["transcripcion"]=f"{n}_{vid}.txt"; v["chars"]=len(t); v["estado"]="OK"
            else: v["estado"]="NO VERIFICABLE: sin subtitulos disponibles"
            res["videos"].append(v); time.sleep(3)
        res["estado"]="OK" if res["videos"] else "NO VERIFICABLE: sin videos en 12 meses"
    except Exception as ex: res["estado"]="NO VERIFICABLE: "+str(ex)[:150]
    json.dump(res,open(f"{out}/{n}.json","w"),ensure_ascii=False,indent=1); time.sleep(2)
