from __future__ import annotations
import json, os, secrets, sqlite3, time, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from .core import CHUMA

VERSION = "0.1.0"
SCHEMA = """
CREATE TABLE IF NOT EXISTS gf_meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gf_users(owner_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_settings(owner_id TEXT PRIMARY KEY, autonomy INTEGER NOT NULL DEFAULT 2, growth_mode TEXT NOT NULL DEFAULT 'organic', daily_limit REAL NOT NULL DEFAULT 0, monthly_limit REAL NOT NULL DEFAULT 0, running INTEGER NOT NULL DEFAULT 0, safe_mode INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS gf_funds(owner_id TEXT PRIMARY KEY, balance REAL NOT NULL DEFAULT 0, reserved REAL NOT NULL DEFAULT 0, spent REAL NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_platforms(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, platform TEXT NOT NULL, status TEXT NOT NULL, connection_method TEXT NOT NULL, legal_class TEXT NOT NULL, note TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_events(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL, detail_json TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_experiments(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, character_id TEXT NOT NULL, hypothesis TEXT NOT NULL, status TEXT NOT NULL, content_id TEXT, target_signal TEXT NOT NULL, result_json TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_signals(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, character_id TEXT NOT NULL, content_id TEXT, kind TEXT NOT NULL, value REAL NOT NULL, confidence REAL NOT NULL, source TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_decisions(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, character_id TEXT, problem TEXT NOT NULL, decision TEXT NOT NULL, evidence_json TEXT NOT NULL, lesson TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_ip_health(character_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, identity REAL NOT NULL, content REAL NOT NULL, audience REAL NOT NULL, learning REAL NOT NULL, economics REAL NOT NULL, total REAL NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_sessions(token TEXT PRIMARY KEY, owner_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
"""

def now(): return int(time.time())
def uid(p): return f"{p}-{uuid.uuid4().hex[:12]}"

class Factory2:
    def __init__(self, path, media_root):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()
        self.chuma = CHUMA(self.path, media_root)
    def close(self):
        self.chuma.store.close()
        self.db.close()
    def one(self, q, p=()): return self.db.execute(q,p).fetchone()
    def all(self, q, p=()): return self.db.execute(q,p).fetchall()
    def commit(self): self.db.commit()
    def event(self, owner, kind, detail):
        self.db.execute("INSERT INTO gf_events VALUES(?,?,?,?,?)",(uid("GF"),owner,kind,json.dumps(detail,ensure_ascii=False),now()))
        self.commit()
    def create_owner(self, username, password):
        if self.one("SELECT 1 FROM gf_users WHERE username=?",(username,)):
            raise ValueError("username_exists")
        import hashlib
        salt=secrets.token_hex(16)
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),180000).hex()
        owner=self.chuma.owner()
        self.db.execute("INSERT INTO gf_users VALUES(?,?,?,?)",(owner,username,salt+"$"+digest,now()))
        self.db.execute("INSERT INTO gf_settings(owner_id) VALUES(?)",(owner,))
        self.db.execute("INSERT INTO gf_funds(owner_id,updated_at) VALUES(?,?)",(owner,now()))
        self.commit()
        self.event(owner,"OWNER_CREATED",{"username":username})
        return owner
    def verify(self, username, password):
        import hashlib, hmac
        row=self.one("SELECT owner_id,password_hash FROM gf_users WHERE username=?",(username,))
        if not row: return None
        salt,digest=row["password_hash"].split("$",1)
        check=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),180000).hex()
        return row["owner_id"] if hmac.compare_digest(check,digest) else None
    def session(self, owner):
        self.db.execute("DELETE FROM gf_sessions WHERE expires_at<=?",(now(),))
        token=secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO gf_sessions VALUES(?,?,?)",(token,owner,now()+86400))
        self.commit()
        return token
    def owner_from_token(self, token):
        row=self.one("SELECT owner_id FROM gf_sessions WHERE token=? AND expires_at>?",(token,now()))
        return row["owner_id"] if row else None
    def bootstrap_character(self, owner, name="Леся"):
        row=self.one("SELECT character_id FROM characters WHERE owner_id=? ORDER BY created_at LIMIT 1",(owner,))
        if row: return row["character_id"]
        return self.chuma.create_character(owner,name)
    def dashboard(self, owner):
        settings=self.one("SELECT * FROM gf_settings WHERE owner_id=?",(owner,))
        fund=self.one("SELECT * FROM gf_funds WHERE owner_id=?",(owner,))
        chars=self.all("SELECT character_id,name,state,version FROM characters WHERE owner_id=? ORDER BY created_at",(owner,))
        platforms=self.all("SELECT platform,status,connection_method,legal_class,note FROM gf_platforms WHERE owner_id=? ORDER BY platform",(owner,))
        events=self.all("SELECT kind,detail_json,created_at FROM gf_events WHERE owner_id=? ORDER BY created_at DESC LIMIT 12",(owner,))
        content=self.one("SELECT COUNT(*) n FROM content WHERE owner_id=?",(owner,))["n"]
        pubs=self.one("SELECT COUNT(*) n FROM publications WHERE owner_id=? AND status='PUBLISHED'",(owner,))["n"]
        experiments=self.all("SELECT id,character_id,hypothesis,status,target_signal,content_id,result_json,created_at,updated_at FROM gf_experiments WHERE owner_id=? ORDER BY created_at DESC LIMIT 20",(owner,))
        signals=self.all("SELECT id,character_id,content_id,kind,value,confidence,source,created_at FROM gf_signals WHERE owner_id=? ORDER BY created_at DESC LIMIT 30",(owner,))
        health=self.all("SELECT * FROM gf_ip_health WHERE owner_id=? ORDER BY total DESC",(owner,))
        return {"version":VERSION,"running":bool(settings["running"]),"safe_mode":bool(settings["safe_mode"]),"autonomy":settings["autonomy"],"growth_mode":settings["growth_mode"],"limits":{"daily":settings["daily_limit"],"monthly":settings["monthly_limit"]},"fund":{"balance":fund["balance"],"reserved":fund["reserved"],"spent":fund["spent"]},"characters":[dict(x) for x in chars],"content_count":content,"published_count":pubs,"platforms":[dict(x) for x in platforms],"events":[{"kind":x["kind"],"detail":json.loads(x["detail_json"]),"created_at":x["created_at"]} for x in events],
"experiments":[dict(x) for x in experiments],
"signals":[dict(x) for x in signals],
"ip_health":[dict(x) for x in health]}
    def start(self, owner):
        s=self.one("SELECT * FROM gf_settings WHERE owner_id=?",(owner,))
        if s["safe_mode"]: raise ValueError("safe_mode")
        if s["running"]:
            pending=self.one("SELECT job_id FROM jobs WHERE owner_id=? AND kind='AUTONOMOUS_CYCLE' AND status IN ('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1",(owner,))
            return {"started":True,"already_running":True,"job_id":pending["job_id"] if pending else None,"next":"growth_step"}
        self.db.execute("UPDATE gf_settings SET running=1 WHERE owner_id=?",(owner,))
        self.commit()
        cid=self.bootstrap_character(owner)
        job=self.chuma.enqueue_job(owner,"AUTONOMOUS_CYCLE",{"character_id":cid,"platform":"local-test","max_attempts":3},"gf2-start-"+str(cid))
        self.event(owner,"FACTORY_STARTED",{"character_id":cid,"job_id":job})
        return {"started":True,"job_id":job,"next":"growth_step"}
    def pause(self, owner):
        self.db.execute("UPDATE gf_settings SET running=0 WHERE owner_id=?",(owner,)); self.commit(); self.event(owner,"FACTORY_PAUSED",{}); return {"paused":True}
    def stop(self, owner):
        self.db.execute("UPDATE gf_settings SET running=0,safe_mode=1 WHERE owner_id=?",(owner,)); self.commit(); self.event(owner,"EMERGENCY_STOP",{}); return {"stopped":True,"safe_mode":True}
    def fund(self, owner, amount):
        amount=float(amount)
        if amount<=0 or amount>100000: raise ValueError("invalid_amount")
        self.db.execute("UPDATE gf_funds SET balance=balance+?,updated_at=? WHERE owner_id=?",(amount,now(),owner)); self.commit(); self.event(owner,"FUND_ADDED",{"amount":amount}); return self.one("SELECT * FROM gf_funds WHERE owner_id=?",(owner,))
    def settings(self, owner, patch):
        allowed={"autonomy":int,"growth_mode":str,"daily_limit":float,"monthly_limit":float}
        sets=[]; vals=[]
        for k,typ in allowed.items():
            if k in patch:
                v=typ(patch[k])
                if k=="autonomy" and v not in range(5): raise ValueError("invalid_autonomy")
                if k=="growth_mode" and v not in ("organic","boost","aggressive"): raise ValueError("invalid_growth_mode")
                if k.endswith("limit") and v<0: raise ValueError("invalid_limit")
                sets.append(k+"=?"); vals.append(v)
        if sets:
            vals.append(owner); self.db.execute("UPDATE gf_settings SET "+",".join(sets)+" WHERE owner_id=?",vals); self.commit()
        self.event(owner,"SETTINGS_UPDATED",patch); return self.dashboard(owner)
    def create_experiment(self, owner, character_id, hypothesis, target_signal="engagement"):
        self.one("SELECT character_id FROM characters WHERE character_id=? AND owner_id=?", (character_id, owner)) or (_ for _ in ()).throw(ValueError("character_not_found"))
        eid=uid("EXP"); t=now()
        self.db.execute("INSERT INTO gf_experiments VALUES(?,?,?,?,?,?,?,?,?,?)",(eid,owner,character_id,hypothesis,"PLANNED",None,target_signal,"{}",t,t))
        self.commit(); self.event(owner,"EXPERIMENT_CREATED",{"experiment_id":eid,"character_id":character_id,"hypothesis":hypothesis,"target_signal":target_signal})
        return eid

    def record_signal(self, owner, character_id, kind, value, content_id=None, confidence=0.5, source="system"):
        self.one("SELECT character_id FROM characters WHERE character_id=? AND owner_id=?", (character_id, owner)) or (_ for _ in ()).throw(ValueError("character_not_found"))
        sid=uid("SIG"); self.db.execute("INSERT INTO gf_signals VALUES(?,?,?,?,?,?,?,?,?)",(sid,owner,character_id,content_id,kind,float(value),float(max(0,min(1,confidence))),source,now()))
        self.commit(); self.event(owner,"SIGNAL_RECORDED",{"signal_id":sid,"kind":kind,"value":value,"confidence":confidence})
        return sid

    def evolve_ip_health(self, owner, character_id):
        self.one("SELECT character_id FROM characters WHERE character_id=? AND owner_id=?", (character_id, owner)) or (_ for _ in ()).throw(ValueError("character_not_found"))
        # Initial score is deliberately conservative; it rises only from observed signals.
        sigs=self.all("SELECT kind,value,confidence FROM gf_signals WHERE owner_id=? AND character_id=? ORDER BY created_at DESC LIMIT 100",(owner,character_id))
        engagement=[float(x["value"]) for x in sigs if x["kind"] in ("engagement","like_rate")]
        audience=[float(x["value"]) for x in sigs if x["kind"] in ("views","follows","audience_growth")]
        content=[float(x["value"]) for x in sigs if x["kind"] in ("content_quality","retention")]
        avg=lambda xs: max(0,min(100,(sum(xs)/len(xs))*100)) if xs else 0.0
        identity=100.0
        content_score=avg(content or engagement)
        audience_score=avg(audience)
        learning=min(100.0,len(sigs)*5.0)
        economics=0.0
        total=round(identity*.20+content_score*.20+audience_score*.25+learning*.20+economics*.15,2)
        t=now()
        self.db.execute("INSERT OR REPLACE INTO gf_ip_health VALUES(?,?,?,?,?,?,?,?)",(character_id,owner,identity,content_score,audience_score,learning,economics,total,t))
        self.commit()
        return dict(self.one("SELECT * FROM gf_ip_health WHERE character_id=?",(character_id,)))

    def next_action(self, owner, character_id):
        health=self.evolve_ip_health(owner,character_id)
        recent=self.all("SELECT kind,value,confidence FROM gf_signals WHERE owner_id=? AND character_id=? ORDER BY created_at DESC LIMIT 20",(owner,character_id))
        views=sum(float(x["value"]) for x in recent if x["kind"]=="views")
        engagement=sum(float(x["value"]) for x in recent if x["kind"]=="engagement")
        confidence=sum(float(x["confidence"]) for x in recent)/len(recent) if recent else 0
        fund=self.one("SELECT * FROM gf_funds WHERE owner_id=?",(owner,))
        if fund["balance"]<=0:
            action="ORGANIC_EXPERIMENT"
        elif health["total"]>=70 and confidence>=0.6:
            action="BOOST_TOP_SIGNAL"
        elif health["audience"] >= 50:
            action="GROW_AUDIENCE"
        else:
            action="RUN_NEXT_EXPERIMENT"
        self.event(owner,"NEXT_ACTION_SELECTED",{"character_id":character_id,"action":action,"health":health["total"],"confidence":round(confidence,3),"views":views,"engagement":engagement})
        return {"action":action,"health":health,"budget_available":fund["balance"],"signal_confidence":round(confidence,3)}

    def run_growth_step(self, owner, character_id):
        settings=self.one("SELECT running,safe_mode FROM gf_settings WHERE owner_id=?",(owner,))
        if not settings or settings["safe_mode"]: raise ValueError("safe_mode")
        if not settings["running"]: raise ValueError("factory_paused")
        profile=self.chuma.character_profile(owner,character_id)
        dna=profile.get("content_dna",{})
        preferred=dna.get("preferred_hooks",[])
        hook=preferred[0] if preferred else "visual curiosity"
        hypothesis=f"Hook '{hook}' improves audience response"
        eid=self.create_experiment(owner,character_id,hypothesis,"engagement")
        result=self.chuma.autonomous_cycle(owner,character_id,"local-test")
        content_id=result.get("content_id")
        self.db.execute("UPDATE gf_experiments SET status='RUNNING',content_id=?,updated_at=? WHERE id=?",(content_id,now(),eid)); self.commit()
        if content_id:
            self.record_signal(owner,character_id,"engagement",0.0,content_id,0.1,"awaiting_distribution")
        return {"experiment_id":eid,"content_id":content_id,"cycle":result,"health":self.evolve_ip_health(owner,character_id)}

    def connect_platform(self, owner, platform):
        platform=str(platform or "").strip().lower()
        if not platform or len(platform)>100:
            raise ValueError("invalid_platform")
        # Credentials/passwords are deliberately never accepted or stored here.
        # Compliance is fail-closed: a platform is not GREEN merely because it has an API.
        # GREEN must be explicitly approved/updated for the current jurisdiction and action.
        allowed={}
        legal=allowed.get(platform.lower(),"YELLOW")
        status="READY" if legal=="GREEN" else "OWNER_REVIEW"
        note=("Official API/OAuth connection required." if legal=="GREEN" else "Legal/platform status or action requires owner review before automation.")
        self.db.execute("INSERT OR REPLACE INTO gf_platforms(id,owner_id,platform,status,connection_method,legal_class,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (uid("PLAT"),owner,platform,status,"OAUTH/API",legal,note,now(),now()))
        self.commit(); self.event(owner,"PLATFORM_REGISTERED",{"platform":platform,"legal_class":legal,"status":status})
        return {"platform":platform,"status":status,"legal_class":legal,"connection_method":"OAUTH/API","note":note}
