from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from .global_factory_2 import Factory2, VERSION
from .factory2_ui import send_html

class Handler(BaseHTTPRequestHandler):
    service=None
    def json(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def owner(self):
        v=self.headers.get("Authorization","")
        return self.service.owner_from_token(v[7:].strip()) if v.startswith("Bearer ") else None
    def body(self):
        n=int(self.headers.get("Content-Length","0"))
        if n>1024*1024: raise ValueError("payload_too_large")
        return json.loads(self.rfile.read(n) or "{}")
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
                o=self.service.verify(data.get("username",""),data.get("password",""))
                if not o: return self.json(401,{"error":"invalid_credentials","message":"Неверный логин или пароль."})
                return self.json(200,{"token":self.service.session(o)})
            o=self.owner()
            if not o: return self.json(401,{"error":"unauthorized"})
            if p=="/factory2/api/start": return self.json(200,self.service.start(o))
            if p=="/factory2/api/pause": return self.json(200,self.service.pause(o))
            if p=="/factory2/api/stop": return self.json(200,self.service.stop(o))
            if p=="/factory2/api/fund":
                x=self.service.fund(o,data.get("amount")); return self.json(200,{"balance":x["balance"],"message":"Баланс пополнен."})
            if p=="/factory2/api/settings": return self.json(200,self.service.settings(o,data))
            if p=="/factory2/api/platform": return self.json(200,self.service.connect_platform(o,str(data.get("platform","")).strip()))
            return self.json(404,{"error":"not_found"})
        except ValueError as e: return self.json(400,{"error":str(e)})
        except Exception as e:
            print("GLOBAL FACTORY 2:",type(e).__name__,flush=True)
            return self.json(400,{"error":"request_failed"})
def run_factory2(host="0.0.0.0",port=8097,db="runtime/factory2.db",media_root="runtime/media"):
    service=Factory2(db,media_root); Handler.service=service
    try: HTTPServer((host,port),Handler).serve_forever()
    finally: service.close()
