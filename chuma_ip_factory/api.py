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
        html = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CHUMA IP FACTORY</title><style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#111;color:#eee}h1{margin-bottom:4px}.muted{color:#aaa}.card{background:#1b1b1b;border:1px solid #333;border-radius:14px;padding:18px;margin:16px 0}input,textarea,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #444;background:#222;color:#eee}input,textarea{width:100%;box-sizing:border-box;margin:6px 0 12px}button{cursor:pointer}button:hover{background:#2b2b2b}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:700px){.row{grid-template-columns:1fr}}pre{white-space:pre-wrap;word-break:break-word;background:#0b0b0b;padding:12px;border-radius:8px}.ok{color:#8fda8f}.warn{color:#e7c66a}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-top:14px}.tile{background:#111;border:1px solid #333;border-radius:12px;padding:10px}.tile img{width:100%;height:220px;object-fit:cover;background:#000;border-radius:8px}.tile small{display:block;color:#aaa;margin-top:7px;word-break:break-word}</style></head><body><h1>CHUMA IP FACTORY</h1><div class="muted">Image Content Factory · пользовательский запуск · версия 2.5.6</div><div class="card"><div id="provider">Проверка ядра…</div><button onclick="createOwner()">Создать владельца</button> <button onclick="resetLocal()">Сбросить локальную сессию</button> <button onclick="setToken()">Токен доступа</button><div id="owner" class="muted"></div></div><div class="card"><h2>Персонаж</h2><input id="name" placeholder="Имя персонажа" value="CHUMA"><textarea id="card" rows=3 placeholder="Краткая карточка персонажа (необязательно)"></textarea><button onclick="createCharacter()">Создать персонажа</button><div id="character" class="muted"></div><div style="margin-top:12px"><input id="reference" type="file" accept="image/jpeg,image/png,image/webp"><button onclick="uploadReference()">Загрузить референс</button><div id="reference_status" class="muted"></div></div></div><div class="card"><h2>Автономный цикл</h2><button onclick="cycle()">Запустить цикл</button><div id="result"></div></div><div class="card"><h2>Визуальный результат</h2><button onclick="gallery()">Показать изображения</button><div id="gallery" class="grid"></div></div><div class="card"><h2>Состояние</h2><button onclick="status()">Обновить</button><pre id="status">—</pre></div><script>const $=id=>document.getElementById(id);let owner=localStorage.chuma_owner||'',character=localStorage.chuma_character||'';function show(){if(owner)$("owner").textContent="Owner: "+owner;if(character)$("character").textContent="Character: "+character;}async function j(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});const token=localStorage.chuma_token;if(token)opt.headers.Authorization='Bearer '+token;let r=await fetch(url,opt);let x=await r.json();if(r.status===401){localStorage.removeItem('chuma_token');throw new Error('Требуется токен доступа. Укажи CHUMA_ADMIN_TOKEN владельца облачного сервиса.')} if(!r.ok)throw new Error(x.message||x.error||r.status);return x}async function boot(){try{let cfg=await j('/config');if(cfg.auth_required&&!localStorage.chuma_token){let t=prompt('Введите токен доступа CHUMA:');if(t){localStorage.chuma_token=t.trim();}}let b=await j('/budget');let x=await j('/provider');$("provider").innerHTML='Ядро: <span class="ok">ONLINE</span> · '+x.version+' · provider: '+x.name+(x.connected?'':' · <span class="warn">внешний генератор не подключён</span>')+' · budget: '+b.mode+(b.allow_paid?'':' · <span class="ok">paid OFF</span>')}catch(e){$("provider").textContent='Ошибка: '+e}}function setToken(){const t=prompt('Токен доступа CHUMA:');if(t===null)return;localStorage.chuma_token=t.trim();location.reload();}function resetLocal(){localStorage.removeItem('chuma_token');localStorage.removeItem('chuma_owner');localStorage.removeItem('chuma_character');owner='';character='';$("owner").textContent='';$("character").textContent='';$("status").textContent='—';$("result").innerHTML='';}async function createOwner(){try{let x=await j('/owners',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});owner=x.owner_id;localStorage.chuma_owner=owner;show()}catch(e){alert(e.message)}}async function uploadReference(){if(!owner||!character)return alert('Сначала создайте владельца и персонажа.');const file=$('reference').files[0];if(!file)return alert('Выберите изображение.');try{let r=await fetch('/characters/'+character+'/reference',{method:'POST',headers:{'Content-Type':file.type,'X-Owner-ID':owner,'X-Filename':file.name,...(localStorage.chuma_token?{'Authorization':'Bearer '+localStorage.chuma_token}:{})},body:file});let x=await r.json();if(!r.ok)throw new Error(x.message||x.error||r.status);$('reference_status').textContent='Референс загружен: '+x.asset_id;await status();await gallery()}catch(e){$('reference_status').textContent='Ошибка: '+e.message}}async function createCharacter(){if(!owner)return alert('Сначала нажмите «Создать владельца».');try{let card=$('card').value?{description:$('card').value}:undefined;let x=await j('/characters',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner_id:owner,name:$('name').value||'CHUMA',card})});character=x.character_id;localStorage.chuma_character=character;show();await status()}catch(e){alert(e.message)}}async function cycle(){if(!owner||!character)return alert('Сначала создайте владельца и персонажа.');try{let x=await j('/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner_id:owner,character_id:character,platform:'local-test'})});$('result').innerHTML='<pre>'+JSON.stringify(x,null,2)+'</pre>';let id=x.job_id;let timer=setInterval(async()=>{try{let job=await j('/jobs/'+id);$('result').innerHTML='<pre>'+JSON.stringify(job,null,2)+'</pre>';if(['SUCCEEDED','DEAD_LETTER'].includes(job.status)){clearInterval(timer);await status();await gallery()}}catch(e){clearInterval(timer);$('result').textContent=e.message}},1500)}catch(e){alert(e.message)}}async function gallery(){if(!owner)return;try{let r=await j('/status/'+owner);if(!r.artifacts_detail.length){$('gallery').innerHTML='<div class="muted">Артефактов пока нет.</div>';return;}$('gallery').innerHTML=r.artifacts_detail.map(a=>'<div class="tile"><img src="/artifacts/'+a.artifact_id+'" loading="lazy"><small>'+a.variant+' · '+a.provider+' · '+a.status+'</small></div>').join('')}catch(e){$('gallery').textContent=e.message}}async function status(){if(!owner)return;$("status").textContent='Загрузка…';try{let x=await j('/status/'+owner);$("status").textContent=JSON.stringify(x,null,2)}catch(e){$("status").textContent=e.message}}show();boot();if(owner){status();gallery()}</script></body></html>"""
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
