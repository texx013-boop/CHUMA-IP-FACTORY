#!/usr/bin/env python3
import json, os, re, secrets, subprocess, time
from http.server import BaseHTTPRequestHandler
from socketserver import UnixStreamServer
from pathlib import Path
from urllib.parse import parse_qs

APP_ROOT=Path(os.getenv("APP_ROOT","/opt/chuma"))
CONTROL_ROOT=Path(os.getenv("CHUMA_CONTROL_ROOT",str(APP_ROOT/"control")))
SOCKET_PATH=Path(os.getenv("CHUMA_DEV_SOCKET",str(CONTROL_ROOT/"dev.sock")))
ENV_FILE=Path(os.getenv("CHUMA_ENV_FILE",str(APP_ROOT/"infra/.env")))
DEV_ROOT=Path(os.getenv("CHUMA_DEV_ROOT",str(APP_ROOT/"dev-workspace")))
BACKUP_ROOT=CONTROL_ROOT/"state/dev-backups"
SESSION_FILE=CONTROL_ROOT/"state/control-session"
REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
MAX_FILE=512*1024
SAFE_EXT={".py",".sh",".yml",".yaml",".json",".md",".txt",".html",".css",".js",".service",".conf"}
DENY_PARTS={".git","control","dev-backups","dev-workspace"}
DENY_NAMES={".env",".env.local",".env.production"}

def session_value():
    try:
        raw=SESSION_FILE.read_text().strip().split("|",1)
        if len(raw)==2 and int(raw[1])>int(time.time()): return raw[0]
    except Exception: pass
    return ""

def load_token():
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("CHUMA_ADMIN_TOKEN="): return line.split("=",1)[1].strip().strip('"').strip("'")
    except Exception: pass
    return os.getenv("CHUMA_ADMIN_TOKEN","").strip()

def auth(h):
    for item in h.get("Cookie","").split(";"):
        if item.strip().startswith("chuma_session=") and secrets.compare_digest(item.strip().split("=",1)[1],session_value()): return True
    value=h.get("Authorization",""); supplied=value[7:].strip() if value.startswith("Bearer ") else ""
    token=load_token()
    return bool(token and supplied) and secrets.compare_digest(supplied,token)

def run(*args,timeout=120,cwd=None):
    try:
        p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124,"","Команда превысила лимит времени."

def init_workspace():
    DEV_ROOT.parent.mkdir(parents=True,exist_ok=True)
    if not (DEV_ROOT/".git").exists():
        return run("git","clone","--depth","1","--single-branch",REPO,str(DEV_ROOT),timeout=180)
    rc,out,err=run("git","fetch","origin","main","--depth","1",cwd=DEV_ROOT,timeout=120)
    if rc: return rc,out,err
    return run("git","reset","--hard","origin/main",cwd=DEV_ROOT,timeout=60)

def safe_rel(value):
    value=str(value or "").replace("\\","/").strip().lstrip("/")
    p=Path(value)
    if not value or value.startswith("../") or "/../" in value or any(x in DENY_PARTS for x in p.parts) or p.name in DENY_NAMES or p.suffix.lower() not in SAFE_EXT: return None
    target=(DEV_ROOT/p).resolve()
    try: target.relative_to(DEV_ROOT.resolve())
    except ValueError: return None
    return target

def files():
    if not DEV_ROOT.exists(): return []
    out=[]
    for p in DEV_ROOT.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(DEV_ROOT)
        if any(x in DENY_PARTS for x in rel.parts) or p.name in DENY_NAMES or p.suffix.lower() not in SAFE_EXT: continue
        out.append(str(rel).replace("\\","/"))
    return sorted(out)[:800]

def status():
    rc,branch,err=run("git","status","--short","--branch",cwd=DEV_ROOT)
    rc2,sha,_=run("git","rev-parse","HEAD",cwd=DEV_ROOT)
    return {"ready":DEV_ROOT.exists(),"branch":branch,"sha":sha,"files":len(files())}

def compile_and_test():
    rc,out,err=run("python3","-m","compileall","-q","chuma_ip_factory","run.py",cwd=DEV_ROOT,timeout=120)
    if rc: return {"ok":False,"stage":"compile","output":out,"error":err}
    rc,out,err=run("python3","-m","pytest","-q",cwd=DEV_ROOT,timeout=240)
    return {"ok":rc in (0,5),"stage":"pytest","output":out,"error":err,"exit":rc}

def deploy():
    check=compile_and_test()
    if not check["ok"]: return False,"Проверка не пройдена:\n"+check["output"]+"\n"+check["error"]
    stamp=time.strftime("%Y%m%d-%H%M%S"); backup=BACKUP_ROOT/stamp; backup.mkdir(parents=True,mode=0o700)
    rc,out,err=run("tar","-czf",str(backup/"production.tar.gz"),"--exclude=control","--exclude=agent","--exclude=infra/.env","--exclude=dev-workspace",".",cwd=APP_ROOT,timeout=180)
    if rc: return False,"Резервная копия не создана: "+err
    rc,out,err=run("rsync","-a","--delete","--exclude=.git","--exclude=infra/.env","--exclude=control","--exclude=agent","--exclude=dev-workspace/",str(DEV_ROOT)+"/",str(APP_ROOT)+"/",timeout=180)
    if rc: return False,"Перенос DEV не удался: "+err
    compose=APP_ROOT/"infra/compose-run.sh"; env=APP_ROOT/"infra/.env"; yml=APP_ROOT/"infra/compose.yml"
    rc,out,err=run(str(compose),"--env-file",str(env),"-f",str(yml),"up","-d","--build",timeout=600)
    if rc: return False,"Сборка не удалась. Резервная копия: "+str(backup)+"\n"+err
    for _ in range(30):
        rc,_,_=run("curl","-fsS","--max-time","5","http://127.0.0.1/ready",timeout=10)
        if rc==0: return True,"DEPLOY_OK\nbackup="+str(backup)
        time.sleep(2)
    return False,"Готовность не подтверждена. Резервная копия: "+str(backup)

def rollback():
    backups=sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()]) if BACKUP_ROOT.exists() else []
    if not backups: return False,"Резервных копий нет."
    archive=backups[-1]/"production.tar.gz"
    tmp=CONTROL_ROOT/"state/dev-rollback.tmp"; subprocess.run(["rm","-rf",str(tmp)]); tmp.mkdir(parents=True,mode=0o700)
    rc,out,err=run("tar","-xzf",str(archive),"-C",str(tmp),timeout=180)
    if rc: return False,"Распаковка не удалась: "+err
    rc,out,err=run("rsync","-a","--delete","--exclude=infra/.env","--exclude=control","--exclude=agent","--exclude=dev-workspace/",str(tmp)+"/",str(APP_ROOT)+"/",timeout=180)
    subprocess.run(["rm","-rf",str(tmp)])
    if rc: return False,"Восстановление не удалось: "+err
    compose=APP_ROOT/"infra/compose-run.sh"; env=APP_ROOT/"infra/.env"; yml=APP_ROOT/"infra/compose.yml"
    rc,out,err=run(str(compose),"--env-file",str(env),"-f",str(yml),"up","-d","--build",timeout=600)
    return (rc==0,"ROLLBACK_OK\nrestored="+str(archive) if rc==0 else "Откат выполнен, но сборка не прошла: "+err)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def sendj(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=min(int(self.headers.get("Content-Length","0") or 0),1024*1024); return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if not auth(self.headers): return self.sendj(401,{"error":"unauthorized"})
        if path=="/":
            ui=(APP_ROOT/"infra/mini-ip-dev-ui.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(ui))); self.end_headers(); self.wfile.write(ui); return
        if path=="/api/status":
            if not DEV_ROOT.exists(): init_workspace()
            return self.sendj(200,{"ok":True,"status":status()})
        if path=="/api/files":
            if not DEV_ROOT.exists(): rc,out,err=init_workspace()
            if not DEV_ROOT.exists(): return self.sendj(500,{"error":"workspace_init_failed","detail":err or out})
            return self.sendj(200,{"ok":True,"files":files()})
        if path=="/api/file":
            rel=parse_qs(self.path.split("?",1)[1] if "?" in self.path else "").get("path",[""])[0]; p=safe_rel(rel)
            if not p or not p.exists(): return self.sendj(404,{"error":"file_not_found"})
            if p.stat().st_size>MAX_FILE: return self.sendj(413,{"error":"file_too_large"})
            sha=run("sha256sum",str(p))[1].split()[0]
            return self.sendj(200,{"ok":True,"path":rel,"content":p.read_text(encoding="utf-8"),"sha":sha})
        if path=="/api/backups":
            items=[p.name for p in sorted(BACKUP_ROOT.iterdir(),reverse=True) if p.is_dir()] if BACKUP_ROOT.exists() else []
            return self.sendj(200,{"ok":True,"backups":items[:20]})
        return self.sendj(404,{"error":"not_found"})
    def do_POST(self):
        if not auth(self.headers): return self.sendj(401,{"error":"unauthorized"})
        path=self.path.split("?",1)[0]
        try: data=self.body()
        except Exception: return self.sendj(400,{"error":"invalid_json"})
        if path=="/api/init":
            rc,out,err=init_workspace(); return self.sendj(200 if rc==0 else 500,{"ok":rc==0,"output":out,"error":err,"status":status() if rc==0 else {}})
        if path=="/api/file":
            rel=str(data.get("path","")); content=str(data.get("content","")); p=safe_rel(rel)
            if not p: return self.sendj(400,{"error":"path_not_allowed"})
            if len(content.encode())>MAX_FILE: return self.sendj(413,{"error":"file_too_large"})
            expected=str(data.get("sha",""))
            if p.exists() and expected and not secrets.compare_digest(run("sha256sum",str(p))[1].split()[0],expected): return self.sendj(409,{"error":"file_changed","message":"Файл изменился на сервере. Сначала перечитай его."})
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding="utf-8"); return self.sendj(200,{"ok":True,"sha":run("sha256sum",str(p))[1].split()[0]})
        if path=="/api/test":
            return self.sendj(200,compile_and_test())
        if path=="/api/build":
            rc,out,err=run("docker","compose","build","app",cwd=DEV_ROOT,timeout=600); return self.sendj(200,{"ok":rc==0,"output":out,"error":err})
        if path=="/api/pull":
            rc,out,err=run("git","fetch","origin","main","--depth","1",cwd=DEV_ROOT,timeout=120)
            if rc==0: rc,out,err=run("git","reset","--hard","origin/main",cwd=DEV_ROOT,timeout=60)
            return self.sendj(200,{"ok":rc==0,"output":out,"error":err,"status":status() if rc==0 else {}})
        if path=="/api/deploy":
            ok,out=deploy(); return self.sendj(200 if ok else 409,{"ok":ok,"output":out})
        if path=="/api/rollback":
            ok,out=rollback(); return self.sendj(200 if ok else 409,{"ok":ok,"output":out})
        return self.sendj(404,{"error":"not_found"})

def main():
    CONTROL_ROOT.mkdir(parents=True,exist_ok=True); BACKUP_ROOT.mkdir(parents=True,exist_ok=True)
    try: SOCKET_PATH.unlink()
    except FileNotFoundError: pass
    srv=UnixStreamServer(str(SOCKET_PATH),Handler); os.chmod(SOCKET_PATH,0o660); srv.serve_forever()

if __name__=="__main__": main()
