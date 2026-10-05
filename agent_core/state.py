import json,os,tempfile
from pathlib import Path
from .models import Job,JobState
class StateStore:
 def __init__(self,root):
  self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True); self.jobs=self.root/"jobs"; self.jobs.mkdir(exist_ok=True); self.events=self.root/"events.jsonl"
 def save_job(self,j):
  fd,tmp=tempfile.mkstemp(dir=self.jobs,prefix=".tmp-",text=True)
  try:
   with os.fdopen(fd,"w",encoding="utf8") as f: json.dump(j.to_dict(),f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
   os.replace(tmp,self.jobs/(j.id+".json"))
  finally:
   if os.path.exists(tmp): os.unlink(tmp)
 def load_job(self,jid):
  p=self.jobs/(jid+".json")
  if not p.exists(): return None
  d=json.loads(p.read_text())
  return Job(id=d["id"],task=d["task"],project=d["project"],state=JobState(d["state"]),plan=d.get("plan",[]),result=d.get("result",{}),attempts=d.get("attempts",0),created_at=d["created_at"],updated_at=d["updated_at"],error=d.get("error"),history=d.get("history",[]))
 def list_jobs(self):
  out=[]
  for p in sorted(self.jobs.glob("*.json")):
   try: out.append(json.loads(p.read_text()))
   except Exception: pass
  return out
 def event(self,kind,payload):
  with self.events.open("a",encoding="utf8") as f: f.write(json.dumps({"kind":kind,"payload":payload},ensure_ascii=False)+"\n")
