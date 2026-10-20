import sys,re,os
from playwright.sync_api import sync_playwright
url,out=sys.argv[1],sys.argv[2]; os.makedirs(out,exist_ok=True)
PERS=re.compile(r"email|e-mail|mail|tel|phone|nome|name|cpf|card|cvv",re.I)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True); pg=b.new_context(viewport={"width":412,"height":915},locale="pt-BR").new_page()
    pg.goto(url,wait_until="load",timeout=60000); last="";n=0;stuck=0
    for _ in range(60):
        pg.wait_for_timeout(2500)
        try: body=pg.inner_text("body")
        except: body=""
        sig=pg.url+"|"+body[:150]
        if sig!=last:
            n+=1;stuck=0;last=sig
            pg.screenshot(path=f"{out}/{n:02d}.png",full_page=True); print(n,pg.url[:90],"|",body[:90].replace("\n"," "),flush=True)
        else:
            stuck+=1
            if stuck>=6: print("STOP sin avance"); break
        ins=[i for i in pg.query_selector_all("input:not([type=radio]):not([type=checkbox]):not([type=hidden]), textarea") if i.is_visible()]
        if any(re.search(r"card|cartao|cartão|cvv|cvc|expir|numero.do.cart",(" ".join((i.get_attribute(x) or "") for x in("name","placeholder","id","autocomplete"))),re.I) for i in ins) or re.search(r"checkout\.|pay\.hotmart|payt\.com|/checkout",pg.url,re.I):
            print("STOP pago/checkout",pg.url[:100]); break
        for i in ins:
            at=" ".join((i.get_attribute(x) or "") for x in("type","name","placeholder","id","autocomplete")).lower()
            v="30"
            if re.search("mail",at): v="prueba.funnel@example.com"
            elif re.search("tel|phone|whats|celular",at): v="11987654321"
            elif re.search("nome|name",at): v="Maria Prueba"
            elif re.search("cpf",at): v=""
            elif re.search("peso|weight",at): v="75"
            elif re.search("altura|height",at): v="165"
            try:
                if v: i.fill(v)
            except: pass
        info=pg.evaluate("""()=>{const bad=/pol[ií]tica|termos|privacy|cookie/i;let k=0;const out=[];
          document.querySelectorAll('[data-fx]').forEach(e=>e.removeAttribute('data-fx'));
          for(const e of document.querySelectorAll('button,a,[role=button],label,div,li')){
            const t=(e.innerText||'').trim(); if(t.length<2||t.length>90||bad.test(t)) continue;
            const r=e.getBoundingClientRect(); if(r.width<40||r.height<20) continue;
            if(getComputedStyle(e).cursor!=='pointer'&&e.tagName!=='BUTTON') continue;
            e.setAttribute('data-fx',k); out.push({k,t,y:r.y+scrollY,a:r.width*r.height}); k++;}
          return out}""")
        CONT=re.compile(r"continu|avan|pr[oó]xim|ver |quero|descobr|come[cç]|iniciar|resultado|liberar|garantir|acessar|receber|enviar|calcular|analis",re.I)
        cont=[q for q in info if CONT.search(q["t"])]
        opts=sorted([q for q in info if q not in cont],key=lambda q:q["y"])
        def jsclick(q):
            try: pg.evaluate("k=>{const e=document.querySelector('[data-fx=\"'+k+'\"]');e.scrollIntoView({block:'center'});e.click()}",q["k"])
            except Exception as ex: pass
        if opts:
            n_pick=1 if stuck==0 else min(1+stuck,len(opts))
            for q in opts[:n_pick] if stuck else opts[:1]: jsclick(q); pg.wait_for_timeout(500)
            if stuck>=1 and cont: jsclick(cont[0])
        elif cont: jsclick(cont[0])
    b.close()
