"""Walker generico de quizzes/funnels. Uso: w2.py URL OUTDIR [lang]. Datos de prueba; nunca tarjeta ni pago. Registra checkout_url si llega."""
import sys,re,os,json
from playwright.sync_api import sync_playwright
url,out=sys.argv[1],sys.argv[2]; lang=sys.argv[3] if len(sys.argv)>3 else "pt-BR"; os.makedirs(out,exist_ok=True)
CONT=re.compile(r"continu|avan[cç]|pr[oó]xim|next|siguiente|entendi|ver meu|ver mi|quero|descobr|come[cç]|iniciar|start|resultado|liberar|garantir|acessar|receber|enviar|calcular|analis|sim,|get my|show|reveal|discover|see my|comenzar|empezar",re.I)
BAD=re.compile(r"pol[ií]tica|termos|privacy|cookie|terms|login|entrar",re.I)
CARD=re.compile(r"card|cart[aã]o|cvv|cvc|expir|cc-",re.I)
CHK=re.compile(r"checkout|pay\.hotmart|payt\.com|hotmart\.com|kiwify|eduzz|monetizze|stripe|paypal|pagamento|/pay/",re.I)
log={"steps":[],"checkout_url":"","end":""}
JS_LIST="""()=>{document.querySelectorAll('[data-fx]').forEach(e=>e.removeAttribute('data-fx'));let k=0;const out=[];
 for(const e of document.querySelectorAll('button,a,[role=button],label,li,div,span,p')){
  const t=(e.innerText||'').trim(); if(t.length<2||t.length>110) continue;
  const r=e.getBoundingClientRect(); if(r.width<30||r.height<14) continue;
  const cs=getComputedStyle(e); if(cs.cursor!=='pointer'&&!['BUTTON','A','LABEL'].includes(e.tagName)) continue;
  if(e.children.length>6) continue;
  e.setAttribute('data-fx',k); out.push({k,t,y:r.y+scrollY,len:t.length,tag:e.tagName}); k++;}
 return out}"""
def jsclick(pg,k):
    try: pg.evaluate("k=>{const e=document.querySelector('[data-fx=\"'+k+'\"]');if(e){e.scrollIntoView({block:'center'});e.click()}}",k)
    except Exception: pass
with sync_playwright() as p:
    b=p.chromium.launch(headless=True); pg=b.new_context(viewport={"width":412,"height":915},locale=lang).new_page()
    pg.goto(url,wait_until="load",timeout=60000)
    last="";n=0;stuck=0
    for it in range(90):
        pg.wait_for_timeout(2500)
        try: body=pg.inner_text("body")
        except Exception: body=""
        cur=pg.url
        sig=cur+"|"+body[:200]
        if sig!=last:
            n+=1;stuck=0;last=sig
            pg.screenshot(path=f"{out}/{n:02d}.png",full_page=True)
            log["steps"].append({"n":n,"url":cur,"text":body[:300].replace("\n"," | ")}); print(n,cur[:80],"|",body[:100].replace("\n"," "),flush=True)
        else:
            stuck+=1
            if stuck==2: print("DBG",[ (q["t"][:25],q["tag"]) for q in pg.evaluate(JS_LIST)][:14],flush=True)
            if stuck>=5: log["end"]="sin avance"; break
        from urllib.parse import urlsplit as _u
        if CHK.search(_u(cur).netloc+_u(cur).path) and _u(cur).netloc!=_u(url).netloc:
            log["checkout_url"]=cur; log["end"]="checkout alcanzado (sin pagar)"; break
        ins=[i for i in pg.query_selector_all("input:not([type=radio]):not([type=checkbox]):not([type=hidden]), textarea") if i.is_visible()]
        if any(CARD.search(" ".join((i.get_attribute(x) or "") for x in("name","placeholder","id","autocomplete"))) for i in ins):
            log["checkout_url"]=cur; log["end"]="formulario de tarjeta visible (no se ingresa tarjeta)"; break
        for i in ins:
            at=" ".join((i.get_attribute(x) or "") for x in("type","name","placeholder","id","autocomplete")).lower(); v="30"
            if "mail" in at: v="prueba.funnel@example.com"
            elif re.search("tel|phone|whats|celular",at): v="11987654321"
            elif re.search("nome|name|chamar|llam",at): v="Maria Prueba"
            elif "cpf" in at: v="" 
            elif re.search("peso|weight",at): v="75"
            elif re.search("altura|height",at): v="165"
            try:
                if v: i.fill(v)
            except Exception: pass
        info=[q for q in pg.evaluate(JS_LIST) if not BAD.search(q["t"])]
        cont=[q for q in info if CONT.search(q["t"])]
        opts=sorted([q for q in info if q not in cont and q["tag"]!="A" or (q not in cont and q["len"]<60)],key=lambda q:(q["y"]))
        opts=sorted(opts,key=lambda q:0 if re.search(r'nenhum|nenhuma|none|ninguno|n[aã]o tenho|nada disso',q['t'],re.I) else 1)
        multi=re.search(r"selecione|mais de uma|todas que|select all|marque",body,re.I)
        if stuck==0 and opts and not (cont and not multi and len(opts)==0):
            if multi:
                sel=[]
                for q in opts:
                    if all(abs(q['y']-y)>25 for y in sel): sel.append(q['y']); jsclick(pg,q['k']); pg.wait_for_timeout(500)
                    if len(sel)>=2 or re.search(r'nenhum|nenhuma|none|ninguno|n[aã]o tenho|nada disso',q['t'],re.I): break
                pg.wait_for_timeout(500)
                info=[q for q in pg.evaluate(JS_LIST) if not BAD.search(q["t"])]; cont=[q for q in info if CONT.search(q["t"])]
                if cont: jsclick(pg,cont[-1]["k"])
            else: jsclick(pg,opts[0]["k"])
        elif cont: jsclick(pg,cont[-1]["k"] if stuck%2==0 else cont[0]["k"])
        elif opts: jsclick(pg,opts[min(stuck,len(opts)-1)]["k"])
    log["final_url"]=pg.url
    b.close()
json.dump(log,open(f"{out}/log.json","w"),ensure_ascii=False,indent=1); print("END",log["end"],log["checkout_url"][:120])
