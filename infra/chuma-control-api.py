#!/usr/bin/env python3
import json, os, re, socket, subprocess, time, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import UnixStreamServer

APP_ROOT=Path(os.getenv("APP_ROOT","/opt/chuma"))
CONTROL_ROOT=Path(os.getenv("CHUMA_CONTROL_ROOT",str(APP_ROOT/"control")))
SOCKET_PATH=Path(os.getenv("CHUMA_CONTROL_SOCKET",str(CONTROL_ROOT/"control.sock")))
ENV_FILE=Path(os.getenv("CHUMA_ENV_FILE",str(APP_ROOT/"infra/.env")))
PROJECTS=("SHUMA_SPACE","FILM_COMBAIN","PERSONAL_AI_COMPANION")
ALLOWED_INTENTS={"status","resume","stop","set-task","create-job","safe-mode-on","safe-mode-off","verify","restart-app"}
SAFE_TASK=re.compile(r"^[^\r\n]{1,2000}$")
SAFE_PROJECT=re.compile(r"^[A-Za-z0-9._-]+$")
PAIRING_FILE=CONTROL_ROOT/"state/control-pairing-code"
SESSION_FILE=CONTROL_ROOT/"state/control-session"
SESSION_TTL=30*24*3600
PAIRING_TTL=10*60
PAIRING_META_FILE=CONTROL_ROOT/"state/control-pairing-meta"
SECURE_COOKIE=os.getenv("CHUMA_SECURE_COOKIE","false").strip().lower() in ("1","true","yes","on")
COOKIE_SECURITY="; Secure" if SECURE_COOKIE else ""

def load_token():
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("CHUMA_ADMIN_TOKEN="):
                return line.split("=",1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.getenv("CHUMA_ADMIN_TOKEN","").strip()

def session_value():
    try:
        raw=SESSION_FILE.read_text().strip().split("|",1)
        if len(raw)==2 and int(raw[1]) > int(time.time()):
            return raw[0]
    except Exception:
        pass
    return ""

def issue_session():
    token=secrets.token_urlsafe(32)
    SESSION_FILE.parent.mkdir(parents=True,exist_ok=True)
    SESSION_FILE.write_text(f"{token}|{int(time.time())+SESSION_TTL}")
    os.chmod(SESSION_FILE,0o600)
    return token

def auth_session(value):
    return bool(value) and secrets.compare_digest(value,session_value())

def auth_pair(code):
    try:
        expiry=int(PAIRING_META_FILE.read_text().strip())
        if expiry <= int(time.time()): return False
        expected=PAIRING_FILE.read_text().strip()
        return bool(expected) and secrets.compare_digest(code,expected)
    except Exception:
        return False

def generate_pairing():
    code=secrets.token_urlsafe(18)
    PAIRING_FILE.parent.mkdir(parents=True,exist_ok=True)
    PAIRING_FILE.write_text(code)
    PAIRING_META_FILE.write_text(str(int(time.time())+PAIRING_TTL))
    os.chmod(PAIRING_FILE,0o600); os.chmod(PAIRING_META_FILE,0o600)
    return code

def run(*args, timeout=30):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    return p.returncode,p.stdout.strip(),p.stderr.strip()

def workspace(cmd, project, *extra):
    return run(str(APP_ROOT/"agent/chuma-workspace.sh"),cmd,project,*extra)

def jobq(cmd, *extra):
    return run(str(APP_ROOT/"agent/chuma-job-queue.sh"),cmd,*extra)

def capability(mode, risk):
    return run(str(APP_ROOT/"agent/chuma-capability-firewall.sh"),"check",mode,risk)

def task_meta(project, task):
    return run(str(APP_ROOT/"agent/chuma-task-language.sh"),"parse",project,task)

def operation_meta(project, operation):
    return run(str(APP_ROOT/"agent/chuma-operation-registry.sh"),"meta",project,operation)

def parse_kv(s):
    out={}
    for line in s.splitlines():
        if "=" in line:
            k,v=line.split("=",1); out[k]=v
    return out

class Handler(BaseHTTPRequestHandler):
    server_version="CHUMA-Control-Agent/1.0"
    def log_message(self,*args): pass
    def auth(self):
        for item in self.headers.get("Cookie","").split(";"):
            if item.strip().startswith("chuma_session="):
                return auth_session(item.strip().split("=",1)[1])
        token=load_token()
        value=self.headers.get("Authorization","")
        supplied=value[7:].strip() if value.startswith("Bearer ") else ""
        return bool(token) and bool(supplied) and secrets.compare_digest(supplied,token)
    def sendj(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=min(int(self.headers.get("Content-Length","0") or 0),32768)
        return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path=="/api/pair":
            return self.sendj(405,{"error":"pair_requires_post"})
        if path=="/api/auth/status":
            return self.sendj(200,{"authenticated":self.auth()})
        if path=="/api/auth/logout":
            SESSION_FILE.unlink(missing_ok=True)
            self.send_response(200)
            self.send_header("Set-Cookie","chuma_session=; Path=/control; Max-Age=0; HttpOnly; SameSite=Strict")
            self.end_headers()
            return
        if not self.auth(): return self.sendj(401,{"error":"unauthorized"})
        if path=="/api/operations":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-operation-registry.sh"),"list")
            return self.sendj(200 if rc==0 else 409,{"ok":rc==0,"raw":out})
        if path=="/api/status":
            services={}
            for unit in ("chuma-agent.service","chuma-auto-update.service","chuma-watchdog.service","chuma-security-agent.service","chuma-control.service"):
                rc,_,_=run("systemctl","is-active",unit)
                services[unit]="ok" if rc==0 else "down"
            rc,out,err=run("docker","ps","--format","{{.Names}}|{{.Status}}")
            containers=[dict(zip(("name","status"),x.split("|",1))) for x in out.splitlines() if "|" in x]
            rc,hout,_=run("curl","-fsS","--max-time","5","http://127.0.0.1/health")
            rc2,rout,_=run("curl","-fsS","--max-time","5","http://127.0.0.1/ready")
            return self.sendj(200,{"status":"ok" if rc==0 and rc2==0 else "degraded","services":services,"containers":containers,
                                  "health":json.loads(hout) if hout else None,"ready":json.loads(rout) if rout else None,
                                  "safe_mode":(CONTROL_ROOT/"state/SAFE_MODE").exists(),"timestamp":time.time()})
        if path=="/api/jobs":
            rc,out,err=jobq("list")
            jobs=[]
            for line in out.splitlines():
                parts=line.split("|")
                if len(parts)>=6:
                    jobs.append({"job_id":parts[0],"project":parts[1],"status":parts[2],"stage":parts[3],"mode":parts[4],"updated_at":parts[5]})
            return self.sendj(200 if rc==0 else 409,{"ok":rc==0,"jobs":jobs,"count":len(jobs)})
        if path=="/api/events":
            rc,out,err=jobq("events")
            events=[]
            for line in out.splitlines():
                parts=line.split("|",3)
                if len(parts)==4:
                    events.append({"time":parts[0],"job_id":parts[1],"event":parts[2],"detail":parts[3]})
            return self.sendj(200 if rc==0 else 409,{"ok":rc==0,"events":events[-200:]})
        m=re.fullmatch(r"/api/jobs/(JOB-[0-9]{8})/(approve|deny)",path)
        if m:
            job_id,decision=m.group(1),m.group(2)
            rc,out,err=jobq("get",job_id)
            if rc!=0: return self.sendj(404,{"error":"job_not_found"})
            gate=str(APP_ROOT/"agent/chuma-approval-gate.sh")
            gr,go,ge=run(gate,decision,job_id)
            if gr!=0: return self.sendj(409,{"error":"approval_update_failed","detail":ge})
            if decision=="approve":
                jobq("set-status",job_id,"QUEUED")
            else:
                jobq("set-status",job_id,"CANCELLED","", "owner_denied")
            return self.sendj(200,{"ok":True,"job_id":job_id,"decision":decision})
        m=re.fullmatch(r"/api/jobs/(JOB-[0-9]{8})",path)
        if m:
            rc,out,err=jobq("get",m.group(1))
            return self.sendj(200 if rc==0 else 404,{"ok":rc==0,"job":parse_kv(out) if rc==0 else None,"error":err})
        if path=="/api/capabilities":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-capability-firewall.sh"),"init")
            rc2,out2,err2=run("cat",str(CONTROL_ROOT/"state/capabilities.env"))
            caps={}
            for line in out2.splitlines():
                if "=" in line:
                    k,v=line.split("=",1); caps[k]=v
            return self.sendj(200,{"ok":rc2==0,"capabilities":caps})
        if path=="/api/servers":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-server-registry.sh"),"list")
            return self.sendj(200 if rc==0 else 409,{"ok":rc==0,"servers":out.splitlines()})
        if path=="/api/projects":
            projects=[]
            for p in PROJECTS:
                rc,out,err=workspace("status",p)
                projects.append({"project_id":p,"state":parse_kv(out),"ok":rc==0})
            return self.sendj(200,{"projects":projects})
        m=re.fullmatch(r"/api/workspace/([A-Za-z0-9._-]+)",path)
        if m:
            p=m.group(1); rc,out,err=workspace("status",p)
            return self.sendj(200,{"project_id":p,"ok":rc==0,"state":parse_kv(out),"raw":out})
        m=re.fullmatch(r"/api/history/([A-Za-z0-9._-]+)",path)
        if m:
            p=m.group(1); rc,out,err=workspace("history",p)
            return self.sendj(200,{"project_id":p,"ok":rc==0,"history":out.splitlines()[-100:]})
        return self.sendj(404,{"error":"not_found"})
    def do_POST(self):
        path=self.path.split("?",1)[0]
        if path=="/api/pair":
            code=self.headers.get("X-CHUMA-Pairing-Code","").strip()
            if not auth_pair(code):
                return self.sendj(401,{"error":"invalid_pairing"})
            session=issue_session()
            PAIRING_FILE.unlink(missing_ok=True)
            PAIRING_META_FILE.unlink(missing_ok=True)
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Set-Cookie",f"chuma_session={session}; Path=/control; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Strict{COOKIE_SECURITY}")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if not self.auth(): return self.sendj(401,{"error":"unauthorized"})
        try: data=self.body()
        except Exception: return self.sendj(400,{"error":"invalid_json"})
        m=re.fullmatch(r"/api/jobs/(JOB-[0-9]{8})/(approve|deny)",path)
        if m:
            job_id,decision=m.group(1),m.group(2)
            rc,out,err=jobq("get",job_id)
            if rc!=0: return self.sendj(404,{"error":"job_not_found"})
            gate=str(APP_ROOT/"agent/chuma-approval-gate.sh")
            gr,go,ge=run(gate,decision,job_id)
            if gr!=0: return self.sendj(409,{"error":"approval_update_failed","detail":ge})
            if decision=="approve":
                jobq("set-status",job_id,"QUEUED")
            else:
                jobq("set-status",job_id,"CANCELLED","","owner_denied")
            return self.sendj(200,{"ok":True,"job_id":job_id,"decision":decision})
        if path=="/api/jobs":
            project=str(data.get("project","")).strip()
            task=str(data.get("task","")).strip()
            session=str(data.get("session","mobile-control")).strip() or "mobile-control"
            if not SAFE_PROJECT.fullmatch(project) or not SAFE_TASK.fullmatch(task):
                return self.sendj(400,{"error":"invalid_request"})
            meta_rc,meta_out,meta_err=task_meta(project,task)
            meta=parse_kv(meta_out) if meta_rc==0 else {}
            if meta_rc!=0: return self.sendj(403,{"error":"task_not_allowed","detail":meta_err or "unknown_operation"})
            operation=meta.get("operation","")
            om_rc,om_out,om_err=operation_meta(project,operation)
            om=parse_kv(om_out) if om_rc==0 else {}
            if om_rc!=0: return self.sendj(403,{"error":"operation_not_registered"})
            mode=meta.get("mode","NORMAL"); risk=meta.get("risk",om.get("risk","READ")); cap=meta.get("capability",om.get("capability","READ"))
            if (CONTROL_ROOT/"state/SAFE_MODE").exists(): return self.sendj(423,{"error":"safe_mode"})
            if capability(mode,cap)[0]!=0: return self.sendj(403,{"error":"capability_denied"})
            jrc,jout,jerr=jobq("create",project,task,mode,session,risk)
            if jrc!=0: return self.sendj(409,{"error":"job_create_failed","detail":jerr})
            job_id=jout.splitlines()[-1].strip()
            return self.sendj(202,{"ok":True,"project":project,"operation":operation,"job_id":job_id,"mode":mode,"risk":risk})
        if path!="/api/intent": return self.sendj(404,{"error":"not_found"})
        project=str(data.get("project","")).strip()
        intent=str(data.get("intent","")).strip()
        task=str(data.get("task","")).strip()
        session=str(data.get("session","mobile-control")).strip() or "mobile-control"
        if not SAFE_PROJECT.fullmatch(project) or not intent: return self.sendj(400,{"error":"invalid_request"})
        if intent not in ALLOWED_INTENTS: return self.sendj(403,{"error":"intent_not_allowed"})
        if intent=="resume":
            rc,out,err=workspace("resume",project)
        elif intent=="stop":
            rc,out,err=workspace("stop",project)
        elif intent in ("set-task","create-job"):
            if not SAFE_TASK.fullmatch(task): return self.sendj(400,{"error":"invalid_task"})
            meta_rc,meta_out,meta_err=task_meta(project,task)
            meta=parse_kv(meta_out) if meta_rc==0 else {}
            if meta_rc!=0 or meta.get("project") != project:
                return self.sendj(403,{"error":"task_not_allowed","detail":meta_err or "unknown_operation"})
            operation=meta.get("operation","")
            om_rc,om_out,om_err=operation_meta(project,operation)
            om=parse_kv(om_out) if om_rc==0 else {}
            if om_rc!=0:
                return self.sendj(403,{"error":"operation_not_registered","operation":operation})
            mode=str(meta.get("mode") or "NORMAL")
            risk=str(meta.get("risk") or om.get("risk") or "READ")
            cap=str(meta.get("capability") or om.get("capability") or "READ")
            if (CONTROL_ROOT/"state/SAFE_MODE").exists():
                return self.sendj(423,{"error":"safe_mode","message":"new execution jobs are blocked"})
            cap_rc,cap_out,cap_err=capability(mode,cap)
            if cap_rc!=0:
                return self.sendj(403,{"error":"capability_denied","mode":mode,"capability":cap})
            jrc,jout,jerr=jobq("create",project,task,mode,session,risk)
            if jrc!=0:
                return self.sendj(409,{"error":"job_create_failed","detail":jerr})
            job_id=jout.splitlines()[-1].strip()
            approval="NOT_REQUIRED"
            if risk in ("DEPLOY","DATABASE","DOCKER","SERVER"):
                ar,ao,ae=run(str(APP_ROOT/"agent/chuma-approval-gate.sh"),"request",job_id)
                approval="PENDING" if ar==0 else "GATE_ERROR"
                if ar==0:
                    jobq("set-status",job_id,"BLOCKED","", "owner_approval_required")
                    return self.sendj(202,{"ok":True,"intent":intent,"project":project,"operation":operation,"job_id":job_id,"mode":mode,"risk":risk,"approval":approval})
            if operation=="SET_TASK":
                rc,out,err=workspace("set-task",project,task)
                if rc!=0:
                    jobq("set-status",job_id,"FAILED","","workspace_set_task_failed")
                    return self.sendj(409,{"ok":False,"intent":intent,"project":project,"operation":operation,"job_id":job_id,"output":out,"error":err})
            return self.sendj(200,{"ok":True,"intent":intent,"project":project,"operation":operation,"job_id":job_id,"mode":mode,"risk":risk,"approval":approval})
        elif intent=="safe-mode-on":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-workspace.sh"),"safe-mode","on")
        elif intent=="safe-mode-off":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-workspace.sh"),"safe-mode","off")
        elif intent=="verify":
            rc,out,err=run(str(APP_ROOT/"agent/chuma-control.sh"),"health",timeout=30)
        elif intent=="restart-app":
            rc,out,err=run(str(APP_ROOT/"infra/compose-run.sh"),"--env-file",str(ENV_FILE),"-f",str(APP_ROOT/"infra/compose.yml"),"restart","app",timeout=60)
        else:
            rc,out,err=0,"status",""
        return self.sendj(200 if rc==0 else 409,{"ok":rc==0,"intent":intent,"project":project,"output":out,"error":err})
    
class Server(UnixStreamServer):
    allow_reuse_address=True

def main():
    if len(os.sys.argv)>1 and os.sys.argv[1]=="pair":
        print(generate_pairing())
        return
    CONTROL_ROOT.mkdir(parents=True,exist_ok=True)
    try: SOCKET_PATH.unlink()
    except FileNotFoundError: pass
    srv=Server(str(SOCKET_PATH),Handler)
    os.chmod(SOCKET_PATH,0o666)
    srv.serve_forever()

if __name__=="__main__": main()
