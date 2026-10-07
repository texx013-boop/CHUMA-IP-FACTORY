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
CREATE TABLE IF NOT EXISTS gf_auth_guard(key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_spend_ledger(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, ip_id TEXT, approved INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, note TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_notifications(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gf_attention(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, character_id TEXT, priority INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', created_at INTEGER NOT NULL, resolved_at INTEGER);
CREATE TABLE IF NOT EXISTS gf_compliance_rules(id TEXT PRIMARY KEY, platform TEXT NOT NULL, action TEXT NOT NULL, jurisdiction TEXT NOT NULL, legal_class TEXT NOT NULL, automation_allowed INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL, note TEXT NOT NULL, reviewed_at INTEGER NOT NULL, expires_at INTEGER, UNIQUE(platform,action,jurisdiction));
CREATE TABLE IF NOT EXISTS gf_distributions(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, experiment_id TEXT, content_id TEXT NOT NULL, platform TEXT NOT NULL, state TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, provider TEXT NOT NULL, account_id TEXT, credential_ref TEXT, provenance_json TEXT NOT NULL, result_json TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
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
        self._migrate_schema()
        self.db.commit()
        self.chuma = CHUMA(self.path, media_root)
    def _migrate_schema(self):
        cols={r["name"] for r in self.all("PRAGMA table_info(gf_platforms)")}
        if "account_id" not in cols:
            self.db.execute("ALTER TABLE gf_platforms ADD COLUMN account_id TEXT")
        if "credential_ref" not in cols:
            self.db.execute("ALTER TABLE gf_platforms ADD COLUMN credential_ref TEXT")

    def _platform_connection(self, owner, platform):
        return self.one("SELECT * FROM gf_platforms WHERE owner_id=? AND platform=? ORDER BY updated_at DESC LIMIT 1",
                        (owner, str(platform).strip().lower()))

    def distribution_adapter(self, platform):
        platform=str(platform).strip().lower()
        adapter=EXTERNAL_ADAPTERS.get(platform)
        if adapter is None:
            return ExternalDistributionAdapter(platform)
        return adapter(platform)

    def prepare_distribution(self, owner, content_id, platform, experiment_id=None):
        platform=str(platform or "").strip().lower()
        if not platform or not content_id: raise ValueError("invalid_distribution")
        compliance=self.compliance_status(platform,"publish","RU")
        connection=self._platform_connection(owner,platform)
        if compliance["legal_class"]!="GREEN" or not compliance["automation_allowed"]:
            state="BLOCKED_COMPLIANCE"
        elif not connection or connection["status"]!="READY":
            state="BLOCKED_AUTH"
        else:
            state="QUEUED"
        key=f"dist:{owner}:{content_id}:{platform}"
        existing=self.one("SELECT * FROM gf_distributions WHERE idempotency_key=?",(key,))
        if existing: return dict(existing)
        provenance={"content_id":content_id,"experiment_id":experiment_id,"platform":platform,
                    "compliance":compliance,"connection_method":"OAUTH/API"}
        did=uid("DIST")
        self.db.execute("""INSERT INTO gf_distributions
            (id,owner_id,experiment_id,content_id,platform,state,idempotency_key,provider,account_id,credential_ref,provenance_json,result_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (did,owner,experiment_id,content_id,platform,state,key,platform,
             connection["account_id"] if connection else None,
             connection["credential_ref"] if connection else None,
             json.dumps(provenance,ensure_ascii=False),json.dumps({},ensure_ascii=False),now(),now()))
        self.commit()
        self.event(owner,"DISTRIBUTION_PREPARED",{"distribution_id":did,"platform":platform,"state":state})
        return dict(self.one("SELECT * FROM gf_distributions WHERE id=?",(did,)))

    def submit_distribution(self, owner, distribution_id):
        row=self.one("SELECT * FROM gf_distributions WHERE id=? AND owner_id=?",(distribution_id,owner))
        if not row: raise ValueError("distribution_not_found")
        if row["state"]=="PUBLISHED": return dict(row)
        if row["state"]!="QUEUED": return dict(row)
        compliance=self.compliance_status(row["platform"],"publish","RU")
        connection=self._platform_connection(owner,row["platform"])
        if compliance["legal_class"]!="GREEN" or not compliance["automation_allowed"]:
            self.db.execute("UPDATE gf_distributions SET state='BLOCKED_COMPLIANCE',updated_at=? WHERE id=?",(now(),distribution_id)); self.commit()
            raise ValueError("distribution_blocked_compliance")
        if not connection or connection["status"]!="READY" or not connection["credential_ref"]:
            self.db.execute("UPDATE gf_distributions SET state='BLOCKED_AUTH',updated_at=? WHERE id=?",(now(),distribution_id)); self.commit()
            raise ValueError("distribution_blocked_auth")
        result=self.distribution_adapter(row["platform"]).publish({"content_id":row["content_id"],"account_id":connection["account_id"],"credential_ref":connection["credential_ref"]})
        next_state=result["state"]
        self.db.execute("UPDATE gf_distributions SET state=?,result_json=?,updated_at=? WHERE id=?",
                        (next_state,json.dumps(result,ensure_ascii=False),now(),distribution_id))
        if row["experiment_id"] and next_state in ("SUBMITTED","PUBLISHED"):
            self.db.execute("UPDATE gf_experiments SET status='AWAITING_MEASUREMENT',updated_at=? WHERE id=? AND owner_id=?",
                            (now(),row["experiment_id"],owner))
        self.commit()
        return dict(self.one("SELECT * FROM gf_distributions WHERE id=?",(distribution_id,)))

    def record_external_measurement(self, owner, distribution_id, metrics, confidence=0.5):
        row=self.one("SELECT * FROM gf_distributions WHERE id=? AND owner_id=?",(distribution_id,owner))
        if not row: raise ValueError("distribution_not_found")
        if row["state"]!="PUBLISHED": raise ValueError("distribution_not_published")
        exp=self.one("SELECT character_id FROM gf_experiments WHERE id=? AND owner_id=?",(row["experiment_id"],owner)) if row["experiment_id"] else None
        if not exp: raise ValueError("experiment_not_found")
        clean={str(k):float(v) for k,v in dict(metrics or {}).items() if isinstance(v,(int,float))}
        for kind,value in clean.items():
            self.record_signal(owner,exp["character_id"],kind,value,row["content_id"],confidence,"external")
        self.db.execute("UPDATE gf_distributions SET result_json=?,updated_at=? WHERE id=?",
                        (json.dumps({"metrics":clean,"measurement_mode":"external"},ensure_ascii=False),now(),distribution_id))
        decision=self.learn_from_signal(owner,exp["character_id"])
        if row["experiment_id"]:
            self.db.execute("UPDATE gf_experiments SET status='MEASURED',result_json=?,updated_at=? WHERE id=? AND owner_id=?",
                            (json.dumps({"distribution_id":distribution_id,"measurement_mode":"external",
                                         "metrics":clean,"decision_id":(decision or {}).get("decision_id")},ensure_ascii=False),
                             now(),row["experiment_id"],owner))
        self.commit()
        return {"distribution_id":distribution_id,"measurement_mode":"external","metrics":clean,"learning":decision}

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
    def auth_guard_check(self, key):
        row=self.one("SELECT failures,locked_until FROM gf_auth_guard WHERE key=?",(key,))
        if row and int(row["locked_until"])>now():
            return False
        return True

    def auth_guard_failure(self, key):
        row=self.one("SELECT failures FROM gf_auth_guard WHERE key=?",(key,))
        failures=(int(row["failures"]) if row else 0)+1
        lock=now()+300 if failures>=5 else 0
        self.db.execute("INSERT OR REPLACE INTO gf_auth_guard(key,failures,locked_until,updated_at) VALUES(?,?,?,?)",
                        (key,failures,lock,now()))
        self.commit()

    def auth_guard_success(self, key):
        self.db.execute("DELETE FROM gf_auth_guard WHERE key=?",(key,))
        self.commit()

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
"ip_health":[dict(x) for x in health],
"spend_today":float(self.one("SELECT COALESCE(SUM(amount),0) n FROM gf_spend_ledger WHERE owner_id=? AND status='COMMITTED' AND created_at>=?",(owner,now()-86400))["n"]),
"spend_month":float(self.one("SELECT COALESCE(SUM(amount),0) n FROM gf_spend_ledger WHERE owner_id=? AND status='COMMITTED' AND created_at>=?",(owner,now()-30*86400))["n"]),
"notifications":[dict(x) for x in self.all("SELECT id,level,kind,title,detail,acknowledged,created_at FROM gf_notifications WHERE owner_id=? ORDER BY created_at DESC LIMIT 20",(owner,))],
"attention":[dict(x) for x in self.all("SELECT id,character_id,priority,kind,title,detail,status,created_at FROM gf_attention WHERE owner_id=? AND status='OPEN' ORDER BY priority DESC,created_at DESC LIMIT 20",(owner,))]}
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
    def notify(self, owner, level, kind, title, detail):
        nid=uid("NTF")
        self.db.execute("INSERT INTO gf_notifications VALUES(?,?,?,?,?,?,?,?)",(nid,owner,level,kind,title,detail,0,now()))
        self.commit()
        return nid

    def attention(self, owner, character_id=None, priority=50, kind="INFO", title="", detail=""):
        aid=uid("ATT")
        self.db.execute("INSERT INTO gf_attention VALUES(?,?,?,?,?,?,?,?,?,?)",(aid,owner,character_id,int(priority),kind,title,detail,"OPEN",now(),None))
        self.commit()
        if priority>=80:
            self.notify(owner,"IMPORTANT","ATTENTION",title,detail)
        self.event(owner,"OWNER_ATTENTION",{"attention_id":aid,"priority":priority,"kind":kind,"character_id":character_id})
        return aid

    def resolve_attention(self, owner, attention_id):
        self.db.execute("UPDATE gf_attention SET status='RESOLVED',resolved_at=? WHERE id=? AND owner_id=?",(now(),attention_id,owner))
        self.commit()
        return True

    def learn_from_signal(self, owner, character_id):
        sigs=self.all("""SELECT kind,value,confidence,source FROM gf_signals
                         WHERE owner_id=? AND character_id=?
                           AND source NOT IN ('awaiting_distribution','pending','placeholder')
                         ORDER BY created_at DESC LIMIT 50""",(owner,character_id))
        if not sigs:
            return None
        by={}
        for x in sigs:
            by.setdefault(x["kind"],[]).append(float(x["value"]))
        engagement=sum(by.get("engagement",[]))/len(by.get("engagement",[])) if by.get("engagement") else None
        if engagement is None:
            return None
        target="continue_experiment" if engagement>=0.5 else "change_hook"
        lesson=("Observed measured engagement; preserve the tested hook and iterate."
                if target=="continue_experiment"
                else "Observed measured weak engagement; test a different hook.")
        did=uid("DEC")
        evidence={"signals":len(sigs),"engagement_avg":engagement,"target":target,
                  "measurement_sources":sorted({str(x["source"]) for x in sigs})}
        self.db.execute("INSERT INTO gf_decisions VALUES(?,?,?,?,?,?,?,?)",
                        (did,owner,character_id,"What should the next content experiment do?",
                         target,json.dumps(evidence,ensure_ascii=False),lesson,now()))
        self.commit()
        if target=="change_hook":
            self.attention(owner,character_id,60,"LEARNING","Нужно изменить гипотезу",
                           "Измеренная вовлечённость слабая — следующий эксперимент должен проверить другой hook.")
        return {"decision_id":did,"decision":target,"lesson":lesson,"evidence":evidence}


    def spend(self, owner, amount, category="growth", ip_id=None, approved=False, note=""):
        amount=float(amount)
        if amount<=0 or amount>100000: raise ValueError("invalid_amount")
        settings=self.one("SELECT daily_limit,monthly_limit,safe_mode FROM gf_settings WHERE owner_id=?",(owner,))
        if settings["safe_mode"]: raise ValueError("safe_mode")
        fund=self.one("SELECT balance FROM gf_funds WHERE owner_id=?",(owner,))
        today=float(self.one("SELECT COALESCE(SUM(amount),0) n FROM gf_spend_ledger WHERE owner_id=? AND status='COMMITTED' AND created_at>=?",(owner,now()-86400))["n"])
        month=float(self.one("SELECT COALESCE(SUM(amount),0) n FROM gf_spend_ledger WHERE owner_id=? AND status='COMMITTED' AND created_at>=?",(owner,now()-30*86400))["n"])
        if settings["daily_limit"] and today+amount>settings["daily_limit"]: raise ValueError("daily_spend_limit")
        if settings["monthly_limit"] and month+amount>settings["monthly_limit"]: raise ValueError("monthly_spend_limit")
        if float(fund["balance"])<amount: raise ValueError("insufficient_funds")
        status="COMMITTED" if approved else "PENDING_APPROVAL"
        lid=uid("SPEND")
        self.db.execute("INSERT INTO gf_spend_ledger VALUES(?,?,?,?,?,?,?,?,?)",(lid,owner,category,amount,ip_id,1 if approved else 0,status,note,now()))
        if approved:
            self.db.execute("UPDATE gf_funds SET balance=balance-?,spent=spent+?,updated_at=? WHERE owner_id=?",(amount,amount,now(),owner))
        self.commit()
        if not approved:
            self.notify(owner,"ACTION","SPEND_APPROVAL_REQUIRED","Требуется подтверждение расхода",f"{category}: {amount:.2f}")
        self.event(owner,"SPEND_"+status,{"ledger_id":lid,"amount":amount,"category":category,"approved":approved})
        return {"id":lid,"status":status,"amount":amount,"balance":self.one("SELECT balance FROM gf_funds WHERE owner_id=?",(owner,))["balance"]}

    def acknowledge_notification(self, owner, notification_id):
        self.db.execute("UPDATE gf_notifications SET acknowledged=1 WHERE id=? AND owner_id=?",(notification_id,owner))
        self.commit()
        return True

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
        # Only one unfinished experiment may own a character at a time.
        active=self.one("""SELECT id FROM gf_experiments
                           WHERE owner_id=? AND character_id=?
                             AND status IN ('PLANNED','RUNNING','DISTRIBUTED','AWAITING_MEASUREMENT')
                           ORDER BY created_at DESC LIMIT 1""",(owner,character_id))
        if active:
            return active["id"]
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
        self.db.execute("INSERT OR REPLACE INTO gf_ip_health VALUES(?,?,?,?,?,?,?,?,?)",(character_id,owner,identity,content_score,audience_score,learning,economics,total,t))
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

        # The internal local-test provider completes the whole contour:
        # Character -> Content -> Distribution -> Metrics -> Learning.
        # Its metrics are explicitly fixture/test data, never presented as real audience data.
        result=self.chuma.autonomous_cycle(owner,character_id,"local-test")
        content_id=result.get("content_id")
        publication_id=result.get("publication_id")
        measured=result.get("metrics") or {}
        self.db.execute("UPDATE gf_experiments SET status='DISTRIBUTED',content_id=?,result_json=?,updated_at=? WHERE id=?",
                        (content_id,json.dumps({"publication_id":publication_id,"distribution_mode":"test_fixture",
                                                "measurement_status":"AWAITING_MEASUREMENT"},ensure_ascii=False),now(),eid))
        # The built-in provider returns a measured fixture immediately; external adapters
        # will be able to leave the experiment in AWAITING_MEASUREMENT instead.
        self.db.execute("UPDATE gf_experiments SET status='AWAITING_MEASUREMENT',updated_at=? WHERE id=?",(now(),eid))
        self.commit()

        # Mirror measured metrics into Factory 2 with explicit provenance.
        views=float(measured.get("views",0))
        engagement=(float(measured.get("likes",0))+float(measured.get("comments",0))+
                    float(measured.get("shares",0))+float(measured.get("saves",0)))/max(views,1)
        source="test_fixture" if measured.get("is_test_fixture") else "external"
        self.record_signal(owner,character_id,"engagement",engagement,content_id,0.5,source)
        if "views" in measured:
            self.record_signal(owner,character_id,"views",views,content_id,0.5,source)
        if "follows" in measured:
            self.record_signal(owner,character_id,"follows",float(measured["follows"]),content_id,0.5,source)

        decision=self.learn_from_signal(owner,character_id)
        self.db.execute("UPDATE gf_experiments SET status='MEASURED',result_json=?,updated_at=? WHERE id=?",
                        (json.dumps({"publication_id":publication_id,"measurement_mode":source,
                                     "metrics":measured,"decision_id":(decision or {}).get("decision_id")},
                                    ensure_ascii=False),now(),eid))
        self.commit()
        self.attention(owner,character_id,40,"CYCLE","Новый эксперимент измерен",
                       f"Эксперимент {eid} прошёл локальный контур; источник метрик: {source}.")
        return {"experiment_id":eid,"content_id":content_id,"publication_id":publication_id,
                "cycle":result,"measurement":{"mode":source,"metrics":measured},
                "learning":decision,"health":self.evolve_ip_health(owner,character_id)}

    def compliance_status(self, platform, action="publish", jurisdiction="RU"):
        platform=str(platform or "").strip().lower()
        action=str(action or "publish").strip().lower()
        jurisdiction=str(jurisdiction or "RU").strip().upper()
        row=self.one("""SELECT legal_class,automation_allowed,source,note,reviewed_at,expires_at
                        FROM gf_compliance_rules
                        WHERE platform=? AND action=? AND jurisdiction=?
                          AND (expires_at IS NULL OR expires_at>=?)
                        ORDER BY reviewed_at DESC LIMIT 1""",
                     (platform,action,jurisdiction,now()))
        if not row:
            return {"legal_class":"YELLOW","automation_allowed":False,"source":"default_fail_closed",
                    "note":"No current compliance rule: owner review required before automation.",
                    "reviewed_at":None,"expires_at":None}
        return dict(row)

    def set_compliance_rule(self, owner, platform, action, jurisdiction, legal_class,
                            automation_allowed=False, source="owner_review", note="", expires_at=None):
        if legal_class not in ("GREEN","YELLOW","RED"):
            raise ValueError("invalid_legal_class")
        platform=str(platform or "").strip().lower()
        action=str(action or "").strip().lower()
        jurisdiction=str(jurisdiction or "").strip().upper()
        if not platform or not action or not jurisdiction:
            raise ValueError("invalid_compliance_rule")
        if legal_class=="GREEN" and not bool(automation_allowed):
            raise ValueError("green_requires_automation_allowed")
        rid=uid("COMP")
        self.db.execute("""INSERT OR REPLACE INTO gf_compliance_rules
            (id,platform,action,jurisdiction,legal_class,automation_allowed,source,note,reviewed_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (rid,platform,action,jurisdiction,legal_class,1 if automation_allowed else 0,
             str(source),str(note),now(),int(expires_at) if expires_at else None))
        self.commit()
        self.event(owner,"COMPLIANCE_RULE_UPDATED",{"platform":platform,"action":action,
                                                    "jurisdiction":jurisdiction,"legal_class":legal_class})
        return self.compliance_status(platform,action,jurisdiction)

    def connect_platform(self, owner, platform, account_id=None, credential_ref=None):
        platform=str(platform or "").strip().lower()
        if not platform or len(platform)>100:
            raise ValueError("invalid_platform")
        compliance=self.compliance_status(platform,"publish","RU")
        legal=compliance["legal_class"]
        if account_id and credential_ref:
            ref=str(credential_ref)
            if not ref.startswith(("secret-manager://","oauth://","vault://")):
                raise ValueError("credential_ref_must_be_reference")
        connected=bool(account_id and credential_ref)
        status="READY" if legal=="GREEN" and compliance["automation_allowed"] and connected else "OWNER_REVIEW"
        note=("Official API/OAuth connection reference registered; current compliance rule permits automation."
              if status=="READY" else compliance["note"])
        self.db.execute("INSERT OR REPLACE INTO gf_platforms(id,owner_id,platform,status,connection_method,legal_class,note,created_at,updated_at,account_id,credential_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (uid("PLAT"),owner,platform,status,"OAUTH/API",legal,note,now(),now(),str(account_id) if account_id else None,str(credential_ref) if credential_ref else None))
        self.commit(); self.event(owner,"PLATFORM_REGISTERED",{"platform":platform,"legal_class":legal,"status":status})
        return {"platform":platform,"status":status,"legal_class":legal,"connection_method":"OAUTH/API","note":note}

class ExternalDistributionAdapter:
    """Safe provider contract. Concrete adapters must use official OAuth/API only."""
    mode="adapter_stub"
    def __init__(self, platform): self.platform=platform
    def publish(self, payload):
        return {"state":"SUBMITTED","provider":self.platform,"mode":self.mode,"external_id":None}

EXTERNAL_ADAPTERS = {}
