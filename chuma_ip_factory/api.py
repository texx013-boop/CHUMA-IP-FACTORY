from http.server import BaseHTTPRequestHandler,HTTPServer
import json, os, hmac, threading, time
from .budget import BudgetPolicy
from pathlib import Path
from .core import CHUMA, VERSION

class API(BaseHTTPRequestHandler):
    MAX_BODY_BYTES=1024*1024
    factory=None
    budget_policy=BudgetPolicy()
    admin_token=os.getenv("CHUMA_ADMIN_TOKEN", "").strip()

    def authorized(self):
        if not self.admin_token:
            return True
        value=self.headers.get("Authorization", "")
        token=value[7:].strip() if value.startswith("Bearer ") else ""
        return bool(token) and hmac.compare_digest(token, self.admin_token)

    def require_auth(self):
        if self.authorized():
            return True
        self.sendj(401,{"error":"unauthorized","message":"valid Bearer token required"}, extra={"WWW-Authenticate":"Bearer"})
        return False
    def sendj(self,status,obj,extra=None):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store');
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_html(self):
        html = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CHUMA OS · IP Factory</title>
<style>
:root{--bg:#08090c;--panel:#101217;--panel2:#151820;--line:#242833;--text:#f5f7fb;--muted:#8d94a3;--accent:#b8ff4a;--accent2:#8fe52d;--danger:#ff6b7a;--shadow:0 20px 60px rgba(0,0,0,.35)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -10%,#20270f 0,#0b0d11 34%,var(--bg) 65%);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
button,input,textarea{font:inherit}button{border:0;cursor:pointer} .app{min-height:100vh;display:grid;grid-template-columns:230px 1fr}
.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:rgba(8,9,12,.82);backdrop-filter:blur(20px);padding:24px 16px;display:flex;flex-direction:column}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;letter-spacing:.04em;padding:6px 10px 28px}.logo-mark{width:34px;height:34px;border-radius:10px;background:var(--accent);color:#090b0d;display:grid;place-items:center;font-weight:950}
.nav{display:grid;gap:6px}.nav button{width:100%;text-align:left;padding:11px 12px;border-radius:10px;background:transparent;color:#9da4b2}.nav button.active,.nav button:hover{background:#171a20;color:#fff}.nav .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin-right:10px;vertical-align:middle}
.side-bottom{margin-top:auto;border-top:1px solid var(--line);padding-top:16px}.side-bottom button{width:100%;margin-top:7px;padding:10px;border-radius:9px;background:#14171d;color:#c6cbd5;border:1px solid var(--line)}
main{min-width:0;padding:30px 34px 60px;max-width:1500px;width:100%;margin:auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}.eyebrow{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.16em}.top-title{font-size:25px;font-weight:750;margin-top:3px}.status-pill{display:flex;align-items:center;gap:8px;background:#11151a;border:1px solid var(--line);padding:8px 12px;border-radius:999px;color:#c7ced8}.status-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
.hero{display:grid;grid-template-columns:1.5fr .8fr;gap:18px;margin-bottom:18px}.hero-card,.card{background:linear-gradient(145deg,rgba(20,23,30,.95),rgba(12,14,19,.96));border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}.hero-card{padding:30px;min-height:235px;position:relative;overflow:hidden}.hero-card:after{content:"";position:absolute;width:280px;height:280px;border-radius:50%;right:-100px;top:-130px;background:rgba(184,255,74,.12);filter:blur(4px)}
.hero h1{font-size:42px;line-height:1.02;margin:10px 0 12px;letter-spacing:-.04em}.hero p{color:#aeb4c0;max-width:620px;margin:0}.accent{color:var(--accent)}.hero-actions{display:flex;gap:10px;margin-top:24px}.primary{background:var(--accent);color:#090b0d;padding:11px 17px;border-radius:10px;font-weight:800}.primary:hover{background:#c9ff78}.secondary{background:#191c23;color:#e9ecf2;border:1px solid #2b303b;padding:11px 17px;border-radius:10px}.secondary:hover{background:#222631}
.metric{padding:22px;display:flex;flex-direction:column;justify-content:space-between}.metric-label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.11em}.metric-value{font-size:31px;font-weight:800;margin-top:8px}.metric-note{color:#7e8796;font-size:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{padding:22px}.card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.card h2{font-size:17px;margin:0}.card-sub{font-size:12px;color:var(--muted)}
.field{margin-bottom:14px}.field label{display:block;color:#a8afbb;font-size:12px;margin-bottom:7px}.field input,.field textarea{width:100%;background:#0d1015;color:#f2f4f8;border:1px solid #2a2f39;border-radius:10px;padding:11px 12px;outline:none}.field input:focus,.field textarea:focus{border-color:#65734d;box-shadow:0 0 0 3px rgba(184,255,74,.07)}
.upload{border:1px dashed #39404d;border-radius:14px;padding:18px;text-align:center;background:#0d1014}.upload input{width:100%;color:#9fa7b4}.upload-title{font-weight:650;margin-bottom:4px}.upload-help{font-size:12px;color:var(--muted)}
.preview{margin-top:12px;border-radius:12px;overflow:hidden;background:#080a0d;min-height:80px;display:grid;place-items:center}.preview img{width:100%;max-height:260px;object-fit:contain}
.action-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.action{padding:14px;border-radius:12px;background:#14171d;border:1px solid var(--line);color:#eef1f6;text-align:left}.action strong{display:block;margin-bottom:3px}.action span{font-size:12px;color:var(--muted)}.action:hover{border-color:#414856;background:#191d25}
.gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.tile{background:#0c0f13;border:1px solid var(--line);border-radius:13px;overflow:hidden}.tile img{width:100%;height:240px;display:block;object-fit:cover;background:#08090c}.tile-meta{padding:10px 11px;color:#9ea6b4;font-size:11px}.empty{padding:30px;color:var(--muted);text-align:center;border:1px dashed #2b3039;border-radius:12px}
pre{margin:0;background:#090b0e;border:1px solid var(--line);padding:14px;border-radius:12px;white-space:pre-wrap;word-break:break-word;color:#aeb6c3;font-size:11px;max-height:250px;overflow:auto}.ok{color:var(--accent)}.warn{color:#f2c65b}.muted{color:var(--muted)}.hidden{display:none!important}
@media(max-width:1000px){.app{grid-template-columns:72px 1fr}.sidebar{padding:18px 10px}.logo{justify-content:center;padding-bottom:24px}.logo span:last-child,.nav button span:last-child,.side-bottom button{display:none}.nav button{text-align:center}.hero{grid-template-columns:1fr}.grid2{grid-template-columns:1fr}}
@media(max-width:700px){.app{display:block}.sidebar{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);display:block;padding:10px 12px}.logo{justify-content:flex-start;padding:5px 0 10px}.logo span:last-child{display:block}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap}.nav button span:last-child{display:inline}.side-bottom{display:none}main{padding:20px 14px 40px}.topbar{align-items:flex-start}.top-title{font-size:21px}.hero h1{font-size:34px}.hero-card{padding:23px}.gallery{grid-template-columns:1fr 1fr}.tile img{height:180px}}
</style>
</head>
<body>
<div class="app">
<aside class="sidebar">
  <div class="logo"><div class="logo-mark">C</div><span>CHUMA OS</span></div>
  <nav class="nav">
    <button class="active" onclick="scrollToId('overview')"><span class="dot"></span><span>Обзор</span></button>
    <button onclick="scrollToId('character-card')"><span>◇</span>&nbsp; <span>Персонаж</span></button>
    <button onclick="scrollToId('gallery-card')"><span>▧</span>&nbsp; <span>Контент</span></button>
    <button onclick="scrollToId('state-card')"><span>◌</span>&nbsp; <span>Система</span></button>
  </nav>
  <div class="side-bottom"><div class="muted" style="font-size:11px;padding:0 4px">IP FACTORY · 2.5.6</div><button onclick="setToken()">Токен доступа</button><button onclick="resetLocal()">Сбросить сессию</button></div>
</aside>
<main>
  <div class="topbar" id="overview">
    <div><div class="eyebrow">Image Content Factory</div><div class="top-title">Рабочее пространство</div></div>
    <div class="status-pill"><span class="status-dot"></span><span id="provider">Подключение…</span></div>
  </div>

  <section class="hero">
    <div class="hero-card">
      <div class="eyebrow">CHUMA / CHARACTER LAB</div>
      <h1>Создавай персонажей.<br><span class="accent">Строй IP.</span></h1>
      <p>Единая точка управления персонажем, референсом, генерацией изображений и дальнейшим обучением фабрики.</p>
      <div class="hero-actions"><button class="primary" onclick="cycle()">▶ Запустить производство</button><button class="secondary" onclick="gallery()">Обновить галерею</button></div>
    </div>
    <div class="card metric"><div class="metric-label">Текущий персонаж</div><div class="metric-value" id="metric-name">CHUMA</div><div class="metric-note" id="character">Персонаж ещё не создан</div></div>
  </section>

  <section class="grid2">
    <div class="card" id="character-card">
      <div class="card-head"><div><h2>Персонаж</h2><div class="card-sub">Identity foundation</div></div><span class="eyebrow">01</span></div>
      <div class="field"><label>Имя</label><input id="name" value="CHUMA" placeholder="Имя персонажа"></div>
      <div class="field"><label>Описание</label><textarea id="card" rows="3" placeholder="Коротко опиши характер, визуальный образ и особенности…"></textarea></div>
      <button class="primary" onclick="createCharacter()">Создать персонажа</button>
    </div>

    <div class="card" id="reference-card">
      <div class="card-head"><div><h2>Референс внешности</h2><div class="card-sub">Identity reference</div></div><span class="eyebrow">02</span></div>
      <div class="upload"><div class="upload-title">Загрузи исходное изображение</div><div class="upload-help">JPG, PNG или WebP · до 10 МБ</div><input id="reference" type="file" accept="image/jpeg,image/png,image/webp" onchange="previewReference()"></div>
      <div id="reference_preview" class="preview hidden"></div>
      <div style="display:flex;gap:10px;align-items:center;margin-top:12px"><button class="secondary" onclick="uploadReference()">Сохранить референс</button><span id="reference_status" class="muted"></span></div>
    </div>
  </section>

  <section class="card" style="margin-top:18px">
    <div class="card-head"><div><h2>Производство</h2><div class="card-sub">Автономный production loop</div></div><span class="eyebrow">03</span></div>
    <div class="action-row">
      <button class="action" onclick="cycle()"><strong>Запустить автономный цикл</strong><span>Generate → QC → Publish → Learn</span></button>
      <button class="action" onclick="status()"><strong>Обновить состояние</strong><span>Получить текущие сигналы и прогресс</span></button>
    </div>
    <div id="result" style="margin-top:14px"></div>
  </section>

  <section class="card" id="gallery-card" style="margin-top:18px">
    <div class="card-head"><div><h2>Визуальная библиотека</h2><div class="card-sub">Последние созданные изображения</div></div><button class="secondary" onclick="gallery()">Обновить</button></div>
    <div id="gallery" class="gallery"><div class="empty">Изображения появятся здесь после производства.</div></div>
  </section>

  <section class="card" id="state-card" style="margin-top:18px">
    <div class="card-head"><div><h2>Состояние фабрики</h2><div class="card-sub">Diagnostics / provenance / jobs</div></div><span class="eyebrow">SYSTEM</span></div>
    <pre id="status">—</pre>
  </section>
</main>
</div>
<script>
const $=id=>document.getElementById(id);
let owner=localStorage.chuma_owner||'',character=localStorage.chuma_character||'';
function scrollToId(id){document.getElementById(id)?.scrollIntoView({behavior:'smooth',block:'start'})}
function show(){if(owner)$("character").textContent="ID владельца: "+owner;if(character)$("character").textContent="ID: "+character}
async function j(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});const token=localStorage.chuma_token;if(token)opt.headers.Authorization='Bearer '+token;let r=await fetch(url,opt);let x=await r.json();if(r.status===401){localStorage.removeItem('chuma_token');throw new Error('Требуется токен доступа CHUMA.')}if(!r.ok)throw new Error(x.message||x.error||r.status);return x}
async function boot(){try{let cfg=await j('/config');if(cfg.auth_required&&!localStorage.chuma_token){let t=prompt('Введите токен доступа CHUMA:');if(t){localStorage.chuma_token=t.trim();}}let b=await j('/budget');let x=await j('/provider');$("provider").innerHTML='<span class="ok">ONLINE</span> · '+x.version+' · '+x.name+' · budget '+b.mode+(b.allow_paid?'':' · paid OFF')}catch(e){$("provider").textContent='Ошибка: '+e.message}}
function setToken(){const t=prompt('Токен доступа CHUMA:');if(t===null)return;localStorage.chuma_token=t.trim();location.reload()}
function resetLocal(){localStorage.removeItem('chuma_token');localStorage.removeItem('chuma_owner');localStorage.removeItem('chuma_character');owner='';character='';location.reload()}
async function createOwner(){try{let x=await j('/owners',{method:'POST',body:'{}'});owner=x.owner_id;localStorage.chuma_owner=owner;show()}catch(e){alert(e.message)}}
function previewReference(){const f=$('reference').files[0];if(!f)return;const u=URL.createObjectURL(f);$('reference_preview').innerHTML='<img src="'+u+'">';$('reference_preview').classList.remove('hidden')}
async function uploadReference(){if(!owner||!character)return alert('Сначала создай владельца и персонажа.');const file=$('reference').files[0];if(!file)return alert('Выбери изображение.');try{let r=await fetch('/characters/'+character+'/reference',{method:'POST',headers:{'Content-Type':file.type,'X-Owner-ID':owner,'X-Filename':file.name,...(localStorage.chuma_token?{'Authorization':'Bearer '+localStorage.chuma_token}:{})},body:file});let x=await r.json();if(!r.ok)throw new Error(x.message||x.error||r.status);$('reference_status').innerHTML='<span class="ok">✓ Референс сохранён</span>';await status();await gallery()}catch(e){$('reference_status').textContent='Ошибка: '+e.message}}
async function createCharacter(){if(!owner)return alert('Сначала создай владельца.');try{let card=$('card').value?{description:$('card').value}:undefined;let x=await j('/characters',{method:'POST',body:JSON.stringify({owner_id:owner,name:$('name').value||'CHUMA',card})});character=x.character_id;localStorage.chuma_character=character;$('metric-name').textContent=$('name').value||'CHUMA';show();await status()}catch(e){alert(e.message)}}
async function cycle(){if(!owner||!character)return alert('Сначала создай владельца и персонажа.');try{let x=await j('/jobs',{method:'POST',body:JSON.stringify({owner_id:owner,character_id:character,platform:'local-test'})});$('result').innerHTML='<pre>Производство запущено · '+x.job_id+'</pre>';let id=x.job_id;let timer=setInterval(async()=>{try{let job=await j('/jobs/'+id);$('result').innerHTML='<pre>'+JSON.stringify(job,null,2)+'</pre>';if(['SUCCEEDED','DEAD_LETTER'].includes(job.status)){clearInterval(timer);await status();await gallery()}}catch(e){clearInterval(timer);$('result').textContent=e.message}},1500)}catch(e){alert(e.message)}}
async function gallery(){if(!owner)return;try{let r=await j('/status/'+owner);if(!r.artifacts_detail.length){$('gallery').innerHTML='<div class="empty">Изображения появятся здесь после производства.</div>';return}let token=localStorage.chuma_token;$('gallery').innerHTML='';for(const a of r.artifacts_detail){let tile=document.createElement('div');tile.className='tile';let img=document.createElement('img');img.loading='lazy';try{let rr=await fetch('/artifacts/'+a.artifact_id,{headers:token?{Authorization:'Bearer '+token}:{}});let blob=await rr.blob();img.src=URL.createObjectURL(blob)}catch(e){}tile.appendChild(img);let meta=document.createElement('div');meta.className='tile-meta';meta.textContent=a.variant+' · '+a.provider+' · '+a.status;tile.appendChild(meta);$('gallery').appendChild(tile)}}catch(e){$('gallery').innerHTML='<div class="empty">'+e.message+'</div>'}}
async function status(){if(!owner)return;$("status").textContent='Загрузка…';try{let x=await j('/status/'+owner);$("status").textContent=JSON.stringify(x,null,2)}catch(e){$("status").textContent=e.message}}
show();boot();if(owner){status();gallery()}
</script>
</body>
</html>"""
        b=html.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0'); self.send_header('Pragma','no-cache'); self.send_header('Expires','0'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ('/','/ui','/gallery'):
            return self.send_html()
        if self.path=='/health': return self.sendj(200,{'status':'ok','version':VERSION})
        if self.path=='/ready':
            try:
                self.factory.store.one('SELECT 1')
                return self.sendj(200,{'status':'ready','version':VERSION})
            except Exception as exc:
                return self.sendj(503,{'status':'not_ready','error':type(exc).__name__})
        if self.path=='/config': return self.sendj(200,{'auth_required':bool(self.admin_token),'version':VERSION})
        if self.path=='/budget': return self.sendj(200,self.budget_policy.describe())
        if self.path.startswith('/artifacts/'):
            if not self.require_auth(): return
            aid=self.path.split('/')[-1]
            row=self.factory.store.one('SELECT storage_path,mime_type FROM artifacts WHERE artifact_id=?',(aid,))
            if not row: return self.sendj(404,{'error':'artifact_not_found'})
            p=Path(row['storage_path']).resolve()
            root=Path(self.factory.asset_root).resolve()
            if root not in p.parents: return self.sendj(403,{'error':'forbidden'})
            try: data=p.read_bytes()
            except FileNotFoundError: return self.sendj(404,{'error':'artifact_file_not_found'})
            self.send_response(200); self.send_header('Content-Type',row['mime_type']); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        if not self.require_auth(): return
        if self.path=='/provider': return self.sendj(200,self.factory.provider_status())
        if self.path.startswith('/status/'):
            return self.sendj(200,self.factory.status(self.path.split('/')[-1]))
        if self.path.startswith('/jobs/'):
            job=self.factory.get_job(self.path.split('/')[-1])
            return self.sendj(200,job) if job else self.sendj(404,{'error':'job_not_found'})
        self.sendj(404,{'error':'not_found'})
    def do_POST(self):
        if not self.require_auth(): return
        try:
            n=int(self.headers.get('Content-Length','0'))
            p=self.path; f=self.factory
            if p.startswith('/characters/') and p.endswith('/reference'):
                if n<1 or n>10*1024*1024:
                    return self.sendj(413,{'error':'payload_too_large','message':'reference image must be <= 10 MiB'})
                mime=self.headers.get('Content-Type','').split(';',1)[0].strip().lower()
                owner=self.headers.get('X-Owner-ID','').strip()
                cid=p.split('/')[2] if len(p.split('/'))>2 else ''
                body=self.rfile.read(n)
                result=f.attach_reference(owner,cid,body,mime,self.headers.get('X-Filename','reference'))
                return self.sendj(201,result)
            if n<0 or n>self.MAX_BODY_BYTES:
                return self.sendj(413,{'error':'payload_too_large','message':'request body exceeds 1 MiB'})
            data=json.loads(self.rfile.read(n) or '{}')
            if p=='/owners': return self.sendj(201,{'owner_id':f.owner()})
            if p=='/characters':
                cid=f.create_character(data['owner_id'],data['name'],data.get('card')); return self.sendj(201,{'character_id':cid})
            if p=='/cycle': return self.sendj(200,f.autonomous_cycle(data['owner_id'],data['character_id'],data.get('platform','local-test')))
            if p=='/jobs':
                payload={'character_id':data['character_id'],'platform':data.get('platform','local-test'),'max_attempts':data.get('max_attempts',3)}
                jid=f.enqueue_job(data['owner_id'],'AUTONOMOUS_CYCLE',payload,data.get('idempotency_key'))
                return self.sendj(202,{'job_id':jid,'status':'QUEUED'})
            self.sendj(404,{'error':'not_found'})
        except Exception as e: self.sendj(400,{'error':type(e).__name__,'message':str(e)})

def worker_loop(factory,stop_event):
    while not stop_event.is_set():
        try:
            row=factory.store.one("SELECT job_id FROM jobs WHERE status='QUEUED' AND next_run_at<=? ORDER BY created_at LIMIT 1",(int(time.time()),))
            if row:
                factory.run_job(row['job_id'])
                continue
        except Exception:
            time.sleep(1)
        stop_event.wait(1)

def run(host='127.0.0.1',port=8097,db='runtime/chuma.db',asset_root='runtime/media',image_provider=None,budget_policy=None):
    f=CHUMA(db,asset_root=asset_root,image_provider=image_provider); API.factory=f; API.budget_policy=budget_policy or BudgetPolicy()
    # Autonomous first-run bootstrap is best-effort: it must never prevent the
    # HTTP service from starting. A persistent marker makes the bootstrap idempotent.
    if os.getenv('CHUMA_AUTOSTART', 'true').strip().lower() not in ('0','false','no','off'):
        try:
            marker=f.store.one("SELECT v FROM meta WHERE k='autostart_v1'")
            if not marker:
                owner_row=f.store.one("SELECT owner_id FROM owners ORDER BY created_at LIMIT 1")
                owner_id=owner_row['owner_id'] if owner_row else f.owner()
                char_row=f.store.one("SELECT character_id FROM characters WHERE owner_id=? ORDER BY created_at LIMIT 1",(owner_id,))
                character_id=char_row['character_id'] if char_row else f.create_character(owner_id,'CHUMA',{'description':'Autonomous image-first seed character'})
                f.enqueue_job(owner_id,'AUTONOMOUS_CYCLE',{'character_id':character_id,'platform':'local-test','max_attempts':3},'autostart-v1')
                f.store.db.execute("INSERT INTO meta(k,v) VALUES('autostart_v1',?)",('queued',))
                f.store.commit()
        except Exception as exc:
            print(f"CHUMA autostart bootstrap deferred: {type(exc).__name__}: {exc}", flush=True)
    stop_event=threading.Event()
    threading.Thread(target=worker_loop,args=(f,stop_event),daemon=True,name='chuma-worker').start()
    try:
        HTTPServer((host,port),API).serve_forever()
    finally:
        stop_event.set(); f.store.close()
