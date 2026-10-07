from __future__ import annotations
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from .global_factory_2 import Factory2, VERSION
from .factory2_ui import send_html

class Handler(BaseHTTPRequestHandler):
    service=None
    def json(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def owner(self):
        v=self.headers.get("Authorization","")
        return self.service.owner_from_token(v[7:].strip()) if v.startswith("Bearer ") else None
    def body(self):
        try:
            n=int(self.headers.get("Content-Length","0"))
        except (TypeError, ValueError):
            raise ValueError("invalid_content_length")
        if n < 0: raise ValueError("invalid_content_length")
        if n>1024*1024: raise ValueError("payload_too_large")
        try:
            data=json.loads(self.rfile.read(n) or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(data,dict):
            raise ValueError("invalid_json")
        return data
    def do_GET(self):
        p=urlsplit(self.path).path
        if p in ("/","/factory2"): return send_html(self)
        if p=="/health": return self.json(200,{"status":"ok","version":VERSION})
        if p=="/ready":
            try: self.service.one("SELECT 1"); return self.json(200,{"status":"ready","version":VERSION})
            except Exception: return self.json(503,{"status":"not_ready"})
        if p=="/factory2/api/dashboard":
            o=self.owner()
            if not o: return self.json(401,{"error":"unauthorized"})
            return self.json(200,self.service.dashboard(o))
        return self.json(404,{"error":"not_found"})
    def do_POST(self):
        p=urlsplit(self.path).path
        try:
            data=self.body()
            if p=="/factory2/api/register":
                if len(data.get("username",""))<3 or len(data.get("password",""))<8: return self.json(400,{"error":"invalid_credentials","message":"Логин минимум 3 символа, пароль минимум 8."})
                o=self.service.create_owner(data["username"],data["password"]); return self.json(201,{"token":self.service.session(o)})
            if p=="/factory2/api/login":
                username=str(data.get("username","")).strip()
                guard_key="login:"+username.lower()
                if not self.service.auth_guard_check(guard_key):
                    return self.json(429,{"error":"login_temporarily_locked","message":"Слишком много неудачных попыток. Попробуйте позже."})
                o=self.service.verify(username,data.get("password",""))
                if not o:
                    self.service.auth_guard_failure(guard_key)
                    return self.json(401,{"error":"invalid_credentials","message":"Неверный логин или пароль."})
                self.service.auth_guard_success(guard_key)
                return self.json(200,{"token":self.service.session(o)})
            o=self.owner()
            if not o: return self.json(401,{"error":"unauthorized"})
            if p=="/factory2/api/start": return self.json(200,self.service.start(o))
            if p=="/factory2/api/pause": return self.json(200,self.service.pause(o))
            if p=="/factory2/api/stop": return self.json(200,self.service.stop(o))
            if p=="/factory2/api/fund":
                x=self.service.fund(o,data.get("amount")); return self.json(200,{"balance":x["balance"],"message":"Баланс пополнен."})
            if p=="/factory2/api/spend":
                x=self.service.spend(o,data.get("amount"),str(data.get("category","growth")),data.get("ip_id"),bool(data.get("approved",False)),str(data.get("note","")))
                return self.json(200,x)
            if p=="/factory2/api/notification/ack":
                return self.json(200,{"acknowledged":self.service.acknowledge_notification(o,str(data.get("notification_id","")))})
            if p=="/factory2/api/attention/resolve":
                return self.json(200,{"resolved":self.service.resolve_attention(o,str(data.get("attention_id","")))})
            if p=="/factory2/api/settings": return self.json(200,self.service.settings(o,data))
            if p=="/factory2/api/platform":
                return self.json(200,self.service.connect_platform(o,str(data.get("platform","")).strip(),
                    data.get("account_id"),data.get("credential_ref")))
            if p=="/factory2/api/distribution/prepare":
                return self.json(201,self.service.prepare_distribution(o,str(data.get("content_id","")).strip(),
                    str(data.get("platform","")).strip(),data.get("experiment_id")))
            if p=="/factory2/api/distribution/submit":
                return self.json(200,self.service.submit_distribution(o,str(data.get("distribution_id","")).strip()))
            if p=="/factory2/api/distribution/measurement":
                return self.json(200,self.service.record_external_measurement(
                    o,str(data.get("distribution_id","")).strip(),data.get("metrics") or {},
                    float(data.get("confidence",0.5))))
            if p=="/factory2/api/distribution/poll":
                return self.json(200,self.service.poll_external_measurement(
                    o,str(data.get("distribution_id","")).strip()))
            if p=="/factory2/api/compliance":
                return self.json(200,self.service.set_compliance_rule(
                    o,str(data.get("platform","")).strip(),str(data.get("action","publish")).strip(),
                    str(data.get("jurisdiction","RU")).strip(),str(data.get("legal_class","YELLOW")).strip(),
                    bool(data.get("automation_allowed",False)),str(data.get("source","owner_review")),
                    str(data.get("note","")),data.get("expires_at")))
            if p=="/factory2/api/experiment":
                cid=str(data.get("character_id","")).strip()
                return self.json(201,{"experiment_id":self.service.create_experiment(o,cid,str(data.get("hypothesis","")).strip(),str(data.get("target_signal","engagement")))})
            if p=="/factory2/api/signal":
                cid=str(data.get("character_id","")).strip()
                return self.json(201,{"signal_id":self.service.record_signal(o,cid,str(data.get("kind","engagement")),float(data.get("value",0)),data.get("content_id"),float(data.get("confidence",0.5)),str(data.get("source","owner")))})
            if p=="/factory2/api/growth-step":
                cid=str(data.get("character_id","")).strip()
                return self.json(202,self.service.run_growth_step(o,cid))
            return self.json(404,{"error":"not_found"})
        except ValueError as e:
            return self.json(400,{"error":str(e)})
        except Exception as e:
            print("GLOBAL FACTORY 2:",type(e).__name__,flush=True)
            return self.json(500,{"error":"internal_error"})
def _worker(service, stop):
    while not stop.is_set():
        try:
            row=service.one("""SELECT j.job_id
                FROM jobs j
                JOIN gf_settings s ON s.owner_id=j.owner_id
                WHERE j.status='QUEUED'
                  AND j.next_run_at<=?
                  AND s.running=1
                  AND s.safe_mode=0
                ORDER BY j.created_at LIMIT 1""",(int(time.time()),))
            if row:
                service.chuma.run_job(row["job_id"])
                continue
        except Exception as exc:
            print("GLOBAL FACTORY 2 worker:",type(exc).__name__,flush=True)
        stop.wait(1)

def run_factory2(host="0.0.0.0",port=8097,db="runtime/factory2.db",media_root="runtime/media"):
    service=Factory2(db,media_root); Handler.service=service
    stop=threading.Event()
    threading.Thread(target=_worker,args=(service,stop),daemon=True,name="factory2-worker").start()
    try: HTTPServer((host,port),Handler).serve_forever()
    finally:
        stop.set()
        service.close()
