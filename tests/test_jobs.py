import pathlib, tempfile
from chuma_ip_factory import CHUMA
from chuma_ip_factory.core import ImageProvider

def test_job_queue_is_idempotent_and_runs():
    d=tempfile.TemporaryDirectory()
    c=CHUMA(pathlib.Path(d.name)/"db.sqlite",pathlib.Path(d.name)/"media")
    o=c.owner(); cid=c.create_character(o,"Queue")
    a=c.enqueue_job(o,"AUTONOMOUS_CYCLE",{"character_id":cid,"platform":"local-test","idea":{"mechanic":"user_brief","hook":"Кафе в Москве"}},"same-key")
    b=c.enqueue_job(o,"AUTONOMOUS_CYCLE",{"character_id":cid,"platform":"local-test"},"same-key")
    assert a==b
    result=c.run_job(a)
    assert result["status"]=="SUCCEEDED"
    assert c.store.one("SELECT COUNT(*) n FROM jobs WHERE owner_id=?",(o,))["n"]==1
    content=c.store.one("SELECT idea_json FROM content WHERE owner_id=? ORDER BY created_at DESC LIMIT 1",(o,))
    assert "Кафе в Москве" in content["idea_json"]
    assert c.store.one("SELECT COUNT(*) n FROM signals WHERE owner_id=?",(o,))["n"] == 2
    assert c.store.one("SELECT COUNT(*) n FROM decisions WHERE owner_id=?",(o,))["n"] == 1
    d.cleanup()

def test_job_failure_retries_then_dead_letters():
    class Failing(ImageProvider):
        name="queue-failing"
        def generate(self,request):
            raise RuntimeError("queue_failure")
    d=tempfile.TemporaryDirectory()
    c=CHUMA(pathlib.Path(d.name)/"db.sqlite",pathlib.Path(d.name)/"media",image_provider=Failing())
    o=c.owner(); cid=c.create_character(o,"Failure")
    jid=c.enqueue_job(o,"AUTONOMOUS_CYCLE",{"character_id":cid,"platform":"local-test","max_attempts":2})
    first=c.run_job(jid)
    assert first["status"]=="QUEUED" and first["attempts"]==1
    c.store.db.execute("UPDATE jobs SET next_run_at=0 WHERE job_id=?",(jid,)); c.store.commit()
    second=c.run_job(jid)
    assert second["status"]=="DEAD_LETTER" and second["attempts"]==2
    assert "queue_failure" in second["error"]
    d.cleanup()
