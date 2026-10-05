from dataclasses import dataclass,field,asdict
from enum import Enum
from datetime import datetime,timezone
from typing import Any

def now(): return datetime.now(timezone.utc).isoformat()
class JobState(str,Enum):
 CREATED="CREATED"; QUEUED="QUEUED"; PLANNING="PLANNING"; RUNNING="RUNNING"; TESTING="TESTING"; FIXING="FIXING"; RETESTING="RETESTING"; SECURITY="SECURITY"; REGRESSION="REGRESSION"; BACKUP="BACKUP"; VERIFYING="VERIFYING"; COMPLETED="COMPLETED"; FAILED="FAILED"; RECOVERING="RECOVERING"; ROLLED_BACK="ROLLED_BACK"; CANCELLED="CANCELLED"
@dataclass(frozen=True)
class Project:
 name:str; workspace:str; permissions:tuple[str,...]=("read","write","execute","test","build")
@dataclass
class Job:
 id:str; task:str; project:str; state:JobState=JobState.CREATED; plan:list[dict[str,Any]]=field(default_factory=list); result:dict[str,Any]=field(default_factory=dict); attempts:int=0; created_at:str=field(default_factory=now); updated_at:str=field(default_factory=now); error:str|None=None; history:list[dict[str,Any]]=field(default_factory=list)
 def transition(self,state:JobState,**data):
  self.state=state; self.updated_at=now(); self.history.append({"at":self.updated_at,"state":state.value,**data})
 def to_dict(self):
  d=asdict(self); d["state"]=self.state.value; return d
