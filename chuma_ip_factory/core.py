from __future__ import annotations
import hashlib, json, os, sqlite3, time, uuid, base64, urllib.request, urllib.error

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

VERSION='2.5.3'
SCHEMA_VERSION=9

class CHUMAError(Exception): pass
class AuthorizationError(CHUMAError): pass
class ProviderNotConnected(CHUMAError): pass

def uid(prefix:str)->str: return f"{prefix}-{uuid.uuid4().hex[:12]}"
def now()->int: return int(time.time())
def stable_hash(value:Any)->str: return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

SCHEMA='''
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS owners(owner_id TEXT PRIMARY KEY,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,created_at INTEGER NOT NULL,FOREIGN KEY(owner_id) REFERENCES owners(owner_id));
CREATE TABLE IF NOT EXISTS characters(character_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,name TEXT NOT NULL,state TEXT NOT NULL,card_json TEXT NOT NULL,genome_json TEXT NOT NULL,content_dna_json TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,version INTEGER NOT NULL,FOREIGN KEY(owner_id) REFERENCES owners(owner_id));
CREATE TABLE IF NOT EXISTS assets(asset_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,meta_json TEXT NOT NULL,content_hash TEXT NOT NULL,created_at INTEGER NOT NULL,FOREIGN KEY(character_id) REFERENCES characters(character_id));
CREATE TABLE IF NOT EXISTS content(content_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,idea_json TEXT NOT NULL,status TEXT NOT NULL,production_json TEXT NOT NULL,provenance_json TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,UNIQUE(owner_id,content_id));
CREATE TABLE IF NOT EXISTS experiments(experiment_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,hypothesis TEXT NOT NULL,target_signal TEXT NOT NULL,status TEXT NOT NULL,result_json TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS publications(publication_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,content_id TEXT NOT NULL,platform TEXT NOT NULL,status TEXT NOT NULL,external_id TEXT,metrics_json TEXT NOT NULL,created_at INTEGER NOT NULL,UNIQUE(owner_id,content_id,platform));
CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,content_id TEXT,level TEXT NOT NULL,kind TEXT NOT NULL,value REAL NOT NULL,meta_json TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audience_memory(memory_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,signal_id TEXT,summary TEXT NOT NULL,confidence REAL NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(decision_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT,problem TEXT NOT NULL,decision TEXT NOT NULL,evidence_json TEXT NOT NULL,expected TEXT NOT NULL,actual TEXT,lesson TEXT,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS health(character_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,identity_score REAL NOT NULL,content_score REAL NOT NULL,audience_score REAL NOT NULL,ip_score REAL NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,kind TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL,next_run_at INTEGER NOT NULL,idempotency_key TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,error TEXT,UNIQUE(owner_id,idempotency_key));
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,event_type TEXT NOT NULL,aggregate_type TEXT NOT NULL,aggregate_id TEXT NOT NULL,payload_json TEXT NOT NULL,actor TEXT NOT NULL,created_at INTEGER NOT NULL,correlation_id TEXT,causation_id TEXT,version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit(audit_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,meta_json TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS image_briefs(brief_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,content_id TEXT,brief_json TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,character_id TEXT NOT NULL,content_id TEXT,asset_id TEXT,variant TEXT NOT NULL,mime_type TEXT NOT NULL,storage_path TEXT NOT NULL,content_hash TEXT NOT NULL,provider TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS provider_runs(run_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,provider TEXT NOT NULL,operation TEXT NOT NULL,request_json TEXT NOT NULL,response_json TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS provider_configs(provider TEXT PRIMARY KEY,enabled INTEGER NOT NULL,endpoint TEXT,config_json TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
'''

class _DB:
    def __init__(self, path):
        self.path=path
        self.is_postgres=isinstance(path,str) and path.startswith(('postgres://','postgresql://'))
        if self.is_postgres:
            if psycopg is None:
                raise RuntimeError('psycopg is required for PostgreSQL DATABASE_URL')
            self.conn=psycopg.connect(path, row_factory=dict_row)
        else:
            self.conn=sqlite3.connect(Path(path),check_same_thread=False)
            self.conn.row_factory=sqlite3.Row
    def execute(self,sql,params=()):
        if self.is_postgres:
            sql=sql.replace('INSERT OR REPLACE INTO meta','INSERT INTO meta')
            sql=sql.replace("VALUES('schema_version',?)", "VALUES('schema_version',%s) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v")
            sql=sql.replace('?', '%s')
        return self.conn.execute(sql,params)
    def executescript(self,script):
        if self.is_postgres:
            for statement in script.split(';'):
                statement=statement.strip()
                if statement:
                    self.conn.execute(statement)
        else:
            self.conn.executescript(script)
    def commit(self): self.conn.commit()
    def close(self): self.conn.close()

class Store:
    def __init__(self,path: str|Path):
        self.path=path
        if not (isinstance(path,str) and path.startswith(('postgres://','postgresql://'))):
            p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); self.path=p
        self.db=_DB(path)
        if not self.db.is_postgres: self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('schema_version',?)",(str(SCHEMA_VERSION),)); self.db.commit()
    def close(self): self.db.close()
    def q(self,sql,params=()): return self.db.execute(sql,params).fetchall()
    def one(self,sql,params=()): return self.db.execute(sql,params).fetchone()
    def commit(self): self.db.commit()
    def event(self,owner,event_type,aggregate_type,aggregate_id,payload,actor='SYSTEM',correlation_id=None,causation_id=None,version=1):
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid('EV'),owner,event_type,aggregate_type,aggregate_id,json.dumps(payload,ensure_ascii=False),actor,now(),correlation_id,causation_id,version)); self.commit()
    def audit(self,owner,action,target,meta):
        self.db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(uid('AU'),owner,action,target,json.dumps(meta,ensure_ascii=False),now())); self.commit()

class ImageProvider:
    name='test-local-image'
    connected=True
    def generate(self,request:dict)->dict:
        brief=request.get('brief',{})
        character=str(brief.get('character_name','CHARACTER')).replace('&','&amp;')
        hook=str(brief.get('hook','CHUMA IMAGE')).replace('&','&amp;')
        svg=('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1280" viewBox="0 0 1024 1280">'
             '<rect width="1024" height="1280" fill="#111"/>'
             f'<text x="512" y="580" text-anchor="middle" fill="white" font-size="52" font-family="sans-serif">{character}</text>'
             f'<text x="512" y="660" text-anchor="middle" fill="white" font-size="30" font-family="sans-serif">{hook}</text></svg>').encode()
        return {'asset_id':uid('ASSET'),'kind':'IMAGE','status':'APPROVED',
                'meta':{'provider':self.name,'request':request,'generated_at':now()},
                'content_hash':hashlib.sha256(svg).hexdigest(),'bytes':svg,'mime_type':'image/svg+xml'}

class HTTPImageProvider(ImageProvider):
    name='http-image-provider'
    connected=False
    def __init__(self,endpoint=None,api_key=None,max_attempts=3,timeout=120,retry_delay=0.25):
        self.endpoint=endpoint; self.api_key=api_key; self.connected=bool(endpoint and api_key)
        self.max_attempts=max(1,int(max_attempts)); self.timeout=max(1,int(timeout)); self.retry_delay=max(0.0,float(retry_delay))
    def generate(self,request:dict)->dict:
        if not self.connected: raise ProviderNotConnected('image_provider_not_connected')
        req=urllib.request.Request(self.endpoint,data=json.dumps(request,ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json','Authorization':f'Bearer {self.api_key}'},method='POST')
        last=None
        for attempt in range(1,self.max_attempts+1):
            try:
                with urllib.request.urlopen(req,timeout=self.timeout) as r: response=json.loads(r.read().decode())
                raw=response.get('image_base64')
                if not raw: raise CHUMAError('provider_response_missing_image_base64')
                try: data=base64.b64decode(raw,validate=True)
                except Exception as exc: raise CHUMAError('provider_response_invalid_image_base64') from exc
                return {'asset_id':uid('ASSET'),'kind':'IMAGE','status':'APPROVED',
                        'meta':{'provider':self.name,'request':request,'response_keys':sorted(response.keys()),'attempts':attempt,'max_attempts':self.max_attempts,'generated_at':now()},
                        'content_hash':hashlib.sha256(data).hexdigest(),'bytes':data,'mime_type':response.get('mime_type','image/png')}
            except urllib.error.HTTPError as exc:
                last=exc
                if exc.code not in (429,500,502,503,504) or attempt>=self.max_attempts: raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last=exc
                if attempt>=self.max_attempts: raise
            if self.retry_delay: time.sleep(self.retry_delay*(2**(attempt-1)))
        raise last or CHUMAError('provider_request_failed')

class DistributionProvider:
    name='test-local-distribution'
    connected=True
    def publish(self,content_id:str,platform:str)->dict:
        return {'external_id':f'test-{platform}-{content_id}','platform':platform,'status':'PUBLISHED'}
    def metrics(self,external_id:str)->dict:
        return {'views':1200,'likes':96,'comments':14,'shares':21,'saves':33,'follows':11,'retention':0.42,'is_test_fixture':True}

class CHUMA:
    def __init__(self,db_path='runtime/chuma.db',asset_root='runtime/media',image_provider=None,distribution_provider=None):
        self.store=Store(db_path); self.asset_root=Path(asset_root); self.asset_root.mkdir(parents=True,exist_ok=True)
        self.image_provider=image_provider or ImageProvider(); self.distribution=distribution_provider or DistributionProvider()
    def provider_status(self):
        return {'name':getattr(self.image_provider,'name','unknown'),'connected':bool(getattr(self.image_provider,'connected',False)),'version':VERSION,'retry':{'max_attempts':getattr(self.image_provider,'max_attempts',1),'timeout':getattr(self.image_provider,'timeout',None),'retry_delay':getattr(self.image_provider,'retry_delay',None)}}
    def owner(self):
        oid=uid('OWN'); self.store.db.execute('INSERT INTO owners VALUES(?,?)',(oid,now())); self.store.commit(); self.store.audit(oid,'OWNER_CREATED',oid,{}); return oid
    def session(self,owner):
        if not self.store.one('SELECT 1 FROM owners WHERE owner_id=?',(owner,)): raise AuthorizationError()
        sid=uid('SES'); self.store.db.execute('INSERT INTO sessions VALUES(?,?,?)',(sid,owner,now())); self.store.commit(); return sid
    def _auth(self,owner):
        if not self.store.one('SELECT 1 FROM owners WHERE owner_id=?',(owner,)): raise AuthorizationError()
    def create_character(self,owner,name,card=None):
        self._auth(owner); card=card or {'name':name,'owner_defined':True}
        cid=uid('CH'); t=now(); genome={'immutable':{'identity_lock':True},'editable':{},'learned':{},'emergent':{}}
        dna={'preferred_formats':['single_image','carousel'],'preferred_hooks':[],'successful_mechanics':[],'fatigue':{}}
        self.store.db.execute('INSERT INTO characters VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,owner,name,'BIRTH',json.dumps(card,ensure_ascii=False),json.dumps(genome),json.dumps(dna),t,t,1))
        self.store.db.execute('INSERT INTO health VALUES(?,?,?,?,?,?,?)',(cid,owner,1.0,0.0,0.0,0.0,t)); self.store.commit()
        self.store.event(owner,'CHARACTER_CREATED','CHARACTER',cid,{'name':name}); self.store.event(owner,'DISCOVERY_QUEUED','CHARACTER',cid,{'program':'image-first'}); return cid
    def initialize_character(self,owner,cid):
        self._auth(owner); row=self.store.one('SELECT * FROM characters WHERE character_id=? AND owner_id=?',(cid,owner))
        if not row: raise AuthorizationError()
        existing_assets=self.store.one('SELECT COUNT(*) n FROM assets WHERE owner_id=? AND character_id=?',(owner,cid))['n']
        existing_experiments=self.store.one('SELECT COUNT(*) n FROM experiments WHERE owner_id=? AND character_id=?',(owner,cid))['n']
        if row['state'] == 'BIRTH':
            self.store.db.execute("UPDATE characters SET state='DISCOVERY',updated_at=?,version=version+1 WHERE character_id=?",(now(),cid)); self.store.commit(); self.store.event(owner,'CHARACTER_STATE_CHANGED','CHARACTER',cid,{'state':'DISCOVERY'})
        if existing_assets == 0:
            for kind,meta in [('PORTRAIT',{'angle':'front'}),('PORTRAIT',{'angle':'three_quarter'}),('FULL_BODY',{'angle':'front'}),('EXPRESSION',{'type':'neutral'})]: self._generate_asset(owner,cid,kind,meta)
        if existing_experiments == 0:
            for i in range(3): self.create_experiment(owner,cid,f'Which image mechanic produces stronger recognition signal #{i+1}', 'CHARACTER_RECOGNITION')
        current=self.store.one('SELECT state FROM characters WHERE character_id=? AND owner_id=?',(cid,owner))['state']
        return {'character_id':cid,'assets_created':max(0,4-existing_assets),'experiments_created':max(0,3-existing_experiments),'state':current}
    def _generate_asset(self,owner,cid,kind,meta,brief=None,content_id=None):
        req={'character_id':cid,'kind':kind,'meta':meta,'brief':brief or {}}
        run_id=uid('RUN')
        try:
            result=self.image_provider.generate(req)
        except Exception as exc:
            self.store.db.execute('INSERT INTO provider_runs VALUES(?,?,?,?,?,?,?,?)',
                (run_id,owner,getattr(self.image_provider,'name','unknown'),'IMAGE_GENERATE',
                 json.dumps(req,ensure_ascii=False),
                 json.dumps({'error_type':type(exc).__name__,'error':str(exc)},ensure_ascii=False),
                 'FAILED',now()))
            self.store.commit()
            self.store.event(owner,'IMAGE_GENERATION_FAILED','CHARACTER',cid,
                             {'kind':kind,'content_id':content_id,'provider':getattr(self.image_provider,'name','unknown'),
                              'error_type':type(exc).__name__})
            raise
        self.store.db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)',(result['asset_id'],owner,cid,kind,result['status'],json.dumps(result['meta'],ensure_ascii=False),result['content_hash'],now()))
        self.store.db.execute('INSERT INTO provider_runs VALUES(?,?,?,?,?,?,?,?)',(run_id,owner,getattr(self.image_provider,'name','unknown'),'IMAGE_GENERATE',json.dumps(req,ensure_ascii=False),json.dumps({'content_hash':result['content_hash'],'mime_type':result.get('mime_type'),'provider_meta':result.get('meta',{})},ensure_ascii=False),'SUCCEEDED',now()))
        if result.get('bytes') is not None:
            ext='svg' if result.get('mime_type')=='image/svg+xml' else 'bin'
            path=self.asset_root/f"{result['asset_id']}.{ext}"; path.write_bytes(result['bytes'])
            self.store.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uid('ART'),owner,cid,content_id,result['asset_id'],'master',result.get('mime_type','application/octet-stream'),str(path),result['content_hash'],getattr(self.image_provider,'name','unknown'),'READY',now()))
        self.store.commit(); self.store.event(owner,'IMAGE_GENERATED','ASSET',result['asset_id'],{'kind':kind,'content_id':content_id,'provider':getattr(self.image_provider,'name','unknown')}); return result['asset_id']
    def create_experiment(self,owner,cid,hypothesis,target):
        self._auth(owner); eid=uid('EXP'); t=now(); self.store.db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',(eid,owner,cid,hypothesis,target,'DESIGNED','{}',t,t)); self.store.commit(); self.store.event(owner,'EXPERIMENT_DESIGNED','EXPERIMENT',eid,{'hypothesis':hypothesis}); return eid
    def next_action(self,owner,cid):
        self._auth(owner); c=self.store.one('SELECT * FROM characters WHERE character_id=? AND owner_id=?',(cid,owner))
        if not c: raise AuthorizationError()
        pending=self.store.one("SELECT * FROM experiments WHERE character_id=? AND owner_id=? AND status IN ('DESIGNED','QUEUED') ORDER BY created_at LIMIT 1",(cid,owner))
        if pending: return {'action':'RUN_EXPERIMENT','experiment_id':pending['experiment_id']}
        return {'action':'CREATE_IMAGE_CONTENT','reason':'no pending experiment'}
    def create_content(self,owner,cid,idea=None):
        self._auth(owner); character=self.store.one('SELECT name FROM characters WHERE character_id=? AND owner_id=?',(cid,owner))
        if not character: raise AuthorizationError()
        assets=self.store.q("SELECT * FROM assets WHERE character_id=? AND owner_id=? AND status='APPROVED' ORDER BY created_at",(cid,owner))
        idea=idea or {'mechanic':'identity_discovery','hook':'visual curiosity'}
        brief={'character_id':cid,'character_name':character['name'],'mechanic':idea.get('mechanic'),'hook':idea.get('hook'),'format':'portrait_social','identity_lock':True,'reuse_policy':'prefer_approved_assets'}
        content_id=uid('CNT'); t=now(); chosen=[a['asset_id'] for a in assets[:2]]
        if not chosen: chosen=[self._generate_asset(owner,cid,'TARGETED',{'reason':'content_gap'},brief=brief,content_id=content_id)]
        brief_id=uid('BRF'); production={'mode':'ASSEMBLY','asset_ids':chosen,'variants':['1:1','4:5','9:16'],'brief_id':brief_id}
        prov={'character_id':cid,'asset_ids':chosen,'schema_version':SCHEMA_VERSION,'engine_version':VERSION,'provider':getattr(self.image_provider,'name','unknown')}
        self.store.db.execute('INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)',(content_id,owner,cid,json.dumps(idea), 'QC_PENDING',json.dumps(production),json.dumps(prov),t,t))
        self.store.db.execute('INSERT INTO image_briefs VALUES(?,?,?,?,?,?,?,?)',(brief_id,owner,cid,content_id,json.dumps(brief,ensure_ascii=False),'READY',t,t))
        self.store.commit(); self.store.event(owner,'IMAGE_BRIEF_CREATED','CONTENT',content_id,brief); self.store.event(owner,'IMAGE_CONTENT_ASSEMBLED','CONTENT',content_id,production); return content_id
    def produce_variants(self,owner,content_id):
        self._auth(owner); row=self.store.one('SELECT * FROM content WHERE content_id=? AND owner_id=?',(content_id,owner))
        if not row: raise AuthorizationError()
        prod=json.loads(row['production_json']); artifacts=[]
        for variant in prod.get('variants',[]):
            existing=self.store.one('SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? AND variant=?',(owner,content_id,variant))
            if existing:
                artifacts.append(existing['artifact_id']); continue
            aid=prod['asset_ids'][0]; src=self.store.one("SELECT * FROM artifacts WHERE asset_id=? AND owner_id=? ORDER BY created_at LIMIT 1",(aid,owner))
            if not src: continue
            srcpath=Path(src['storage_path']); dest=self.asset_root/f"{content_id}_{variant.replace(':','x')}{srcpath.suffix}"
            raw=srcpath.read_bytes()
            if src['mime_type']=='image/svg+xml':
                # Preserve a true visual master and expose deterministic derived SVGs.
                sizes={'1:1':(1024,1024),'4:5':(1024,1280),'9:16':(1024,1820)}
                w,h=sizes.get(variant,(1024,1280))
                text=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="#111"/><image href="data:image/svg+xml;base64,{base64.b64encode(raw).decode()}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet"/></svg>'
                raw=text.encode()
                dest=dest.with_suffix('.svg')
            dest.write_bytes(raw); ah=hashlib.sha256(raw).hexdigest(); arid=uid('ART')
            self.store.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(arid,owner,row['character_id'],content_id,aid,variant,src['mime_type'],str(dest),ah,src['provider'],'READY',now())); artifacts.append(arid)
        self.store.commit(); self.store.event(owner,'IMAGE_VARIANTS_CREATED','CONTENT',content_id,{'count':len(artifacts)}); return artifacts
    def qc(self,owner,content_id):
        row=self.store.one('SELECT * FROM content WHERE content_id=? AND owner_id=?',(content_id,owner))
        if not row: raise AuthorizationError()
        prov=json.loads(row['provenance_json']); ok=bool(prov.get('character_id')) and bool(prov.get('asset_ids'))
        status='READY' if ok else 'REJECTED'; self.store.db.execute('UPDATE content SET status=?,updated_at=? WHERE content_id=?',(status,now(),content_id)); self.store.commit(); self.store.event(owner,'IMAGE_QC_PASSED' if ok else 'IMAGE_QC_FAILED','CONTENT',content_id,{'ok':ok}); return status
    def authorize_publish(self,owner,content_id,platform):
        self._auth(owner); row=self.store.one("SELECT status,character_id FROM content WHERE content_id=? AND owner_id=?",(content_id,owner))
        if not row or row['status']!='READY': raise CHUMAError('content_not_ready')
        pub=self.store.one('SELECT * FROM publications WHERE owner_id=? AND content_id=? AND platform=?',(owner,content_id,platform))
        if pub: return pub['publication_id']
        p=uid('PUB'); self.store.db.execute('INSERT INTO publications VALUES(?,?,?,?,?,?,?,?)',(p,owner,content_id,platform,'AUTHORIZED',None,'{}',now())); self.store.commit(); self.store.event(owner,'PUBLICATION_AUTHORIZED','PUBLICATION',p,{'platform':platform}); return p
    def publish(self,owner,publication_id):
        row=self.store.one('SELECT * FROM publications WHERE publication_id=? AND owner_id=?',(publication_id,owner))
        if not row: raise AuthorizationError()
        if row['status']=='PUBLISHED': return row['external_id']
        result=self.distribution.publish(row['content_id'],row['platform']); self.store.db.execute('UPDATE publications SET status=?,external_id=? WHERE publication_id=?',('PUBLISHED',result['external_id'],publication_id)); self.store.commit(); self.store.event(owner,'IMAGE_PUBLISHED','PUBLICATION',publication_id,result); return result['external_id']
    def ingest_metrics_and_learn(self,owner,publication_id):
        row=self.store.one('SELECT * FROM publications WHERE publication_id=? AND owner_id=?',(publication_id,owner))
        if not row or row['status']!='PUBLISHED': raise CHUMAError('not_published')
        m=self.distribution.metrics(row['external_id']); c=self.store.one('SELECT character_id FROM content WHERE content_id=?',(row['content_id'],)); cid=c['character_id']
        engagement=(m['likes']+m['comments']+m['shares']+m['saves'])/max(m['views'],1); follow_rate=m['follows']/max(m['views'],1)
        level='CONTENT'; self.store.db.execute('INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?)',(uid('SIG'),owner,cid,row['content_id'],level,'ENGAGEMENT',engagement,json.dumps(m),now()))
        self.store.db.execute('INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?)',(uid('SIG'),owner,cid,row['content_id'],'CHARACTER','FOLLOW_CONVERSION',follow_rate,json.dumps(m),now()))
        summary=f'Local test signal: engagement={engagement:.4f}, follow_rate={follow_rate:.4f}'
        self.store.db.execute('INSERT INTO audience_memory VALUES(?,?,?,?,?,?,?)',(uid('MEM'),owner,cid,None,summary,min(1.0,engagement*10),now()))
        dna=json.loads(self.store.one('SELECT content_dna_json FROM characters WHERE character_id=?',(cid,))['content_dna_json']); dna['successful_mechanics'].append({'content_id':row['content_id'],'engagement':engagement}); dna['fatigue']['identity_discovery']=len(dna['successful_mechanics'])
        self.store.db.execute('UPDATE characters SET content_dna_json=?,updated_at=?,version=version+1,state=? WHERE character_id=?',(json.dumps(dna),now(),'FORMATION' if engagement>=0.03 else 'DISCOVERY',cid))
        self.store.db.execute('UPDATE health SET content_score=?,audience_score=?,updated_at=? WHERE character_id=?',(min(1,engagement*20),min(1,follow_rate*100),now(),cid)); self.store.commit()
        self.store.event(owner,'METRICS_RECEIVED','PUBLICATION',publication_id,m); self.store.event(owner,'LEARNING_CREATED','CHARACTER',cid,{'engagement':engagement,'follow_rate':follow_rate})
        did=uid('DEC'); self.store.db.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?,?)',(did,owner,cid,'What should next content test?','Reuse successful mechanic with controlled variation',json.dumps({'engagement':engagement,'follow_rate':follow_rate}), 'higher repeatability',None,None,now())); self.store.commit(); return {'metrics':m,'decision_id':did,'character_id':cid}
    def autonomous_cycle(self,owner,cid,platform='local-test'):
        self._auth(owner)
        init=self.initialize_character(owner,cid)
        content=self.create_content(owner,cid)
        self.qc(owner,content)
        variants=self.produce_variants(owner,content)
        pub=self.authorize_publish(owner,content,platform)
        external_id=self.publish(owner,pub)
        learned=self.ingest_metrics_and_learn(owner,pub)
        return {'character_id':cid,'content_id':content,'publication_id':pub,'external_id':external_id,'variants':len(variants),'initialization':init,'next_action':self.next_action(owner,cid),**learned}
    def enqueue_job(self,owner,kind,payload,idempotency_key=None):
        self._auth(owner)
        key=idempotency_key or stable_hash({'kind':kind,'payload':payload})
        existing=self.store.one('SELECT job_id FROM jobs WHERE owner_id=? AND idempotency_key=?',(owner,key))
        if existing: return existing['job_id']
        jid=uid('JOB'); t=now()
        self.store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(jid,owner,kind,json.dumps(payload,ensure_ascii=False),'QUEUED',0,t,key,t,t,None)); self.store.commit()
        self.store.event(owner,'JOB_QUEUED','JOB',jid,{'kind':kind,'idempotency_key':key})
        return jid
    def claim_job(self,job_id=None):
        if job_id:
            row=self.store.one("SELECT * FROM jobs WHERE job_id=? AND status='QUEUED' AND next_run_at<=?",(job_id,now()))
        else:
            row=self.store.one("SELECT * FROM jobs WHERE status='QUEUED' AND next_run_at<=? ORDER BY created_at LIMIT 1",(now(),))
        if not row: return None
        cur=self.store.db.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,updated_at=? WHERE job_id=? AND status='QUEUED'",(now(),row['job_id']))
        self.store.commit()
        if getattr(cur,'rowcount',1) != 1:
            return None
        return self.store.one('SELECT * FROM jobs WHERE job_id=?',(row['job_id'],))
    def get_job(self,job_id):
        row=self.store.one('SELECT * FROM jobs WHERE job_id=?',(job_id,))
        if not row: return None
        out=dict(row); out['payload']=json.loads(out.pop('payload_json')); return out
    def run_job(self,job_id):
        row=self.claim_job(job_id)
        if not row: return self.get_job(job_id)
        payload=json.loads(row['payload_json']); owner=row['owner_id']
        try:
            if row['kind']=='AUTONOMOUS_CYCLE':
                self.autonomous_cycle(owner,payload['character_id'],payload.get('platform','local-test'))
            else:
                raise CHUMAError('unknown_job_kind')
            self.store.db.execute("UPDATE jobs SET status='SUCCEEDED',updated_at=?,error=NULL WHERE job_id=?",(now(),job_id)); self.store.commit()
            self.store.event(owner,'JOB_SUCCEEDED','JOB',job_id,{'kind':row['kind']})
        except Exception as exc:
            attempts=int(row['attempts']); max_attempts=max(1,int(payload.get('max_attempts',3)))
            terminal=attempts>=max_attempts
            status='DEAD_LETTER' if terminal else 'QUEUED'
            delay=min(300,2**max(0,attempts-1))
            self.store.db.execute("UPDATE jobs SET status=?,next_run_at=?,updated_at=?,error=? WHERE job_id=?",(status,now() if terminal else now()+delay,now(),f'{type(exc).__name__}: {exc}',job_id)); self.store.commit()
            self.store.event(owner,'JOB_DEAD_LETTERED' if terminal else 'JOB_RETRY_SCHEDULED','JOB',job_id,{'attempt':attempts,'max_attempts':max_attempts,'error':str(exc),'retry_in':delay})
        return self.get_job(job_id)
    def status(self,owner):
        self._auth(owner); out={}
        for table in ['characters','assets','content','experiments','publications','signals','audience_memory','decisions','jobs','events','audit','image_briefs','artifacts','provider_runs']:
            out[table]=self.store.one(f'SELECT COUNT(*) n FROM {table} WHERE owner_id=?',(owner,))['n']
        out['version']=VERSION; out['schema_version']=SCHEMA_VERSION
        out['jobs_detail']=[self.get_job(r['job_id']) for r in self.store.q('SELECT job_id FROM jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 20',(owner,))]
        chars=self.store.q('SELECT character_id,name,state,version FROM characters WHERE owner_id=? ORDER BY created_at',(owner,))
        out['characters_detail']=[dict(c) for c in chars]
        arts=self.store.q('SELECT artifact_id,character_id,content_id,variant,mime_type,provider,status,created_at FROM artifacts WHERE owner_id=? ORDER BY created_at DESC LIMIT 100',(owner,))
        out['artifacts_detail']=[dict(a) for a in arts]
        return out
