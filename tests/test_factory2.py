import tempfile
from pathlib import Path
from chuma_ip_factory.global_factory_2 import Factory2, VERSION

def test_factory2_owner_dashboard_and_start():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        assert f.dashboard(owner)["running"] is False
        x=f.start(owner)
        assert x["started"] is True
        d=f.dashboard(owner)
        assert d["running"] is True
        assert d["characters"]
        f.close()

def test_factory2_platforms_are_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        x=f.connect_platform(owner,"instagram")
        assert x["legal_class"]=="YELLOW"
        assert x["status"]=="OWNER_REVIEW"
        f.close()

def test_factory2_fund_and_limits():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        x=f.fund(owner,25)
        assert float(x["balance"])==25
        d=f.settings(owner,{"growth_mode":"boost","daily_limit":5,"monthly_limit":50,"autonomy":3})
        assert d["growth_mode"]=="boost"
        assert d["limits"]["daily"]==5.0
        assert d["limits"]["monthly"]==50.0
        assert d["autonomy"]==3
        f.close()

def test_factory2_stop_is_safe():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        x=f.stop(owner)
        assert x["safe_mode"] is True
        try:
            f.start(owner)
            assert False
        except ValueError as e:
            assert str(e)=="safe_mode"
        f.close()

def test_factory2_version():
    assert VERSION=="0.1.0"


def test_factory2_experiment_signal_and_health():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        eid=f.create_experiment(owner,cid,"Test hook improves engagement","engagement")
        assert eid.startswith("EXP-")
        sid=f.record_signal(owner,cid,"engagement",0.72,confidence=0.8)
        assert sid.startswith("SIG-")
        h=f.evolve_ip_health(owner,cid)
        assert h["total"] >= 0
        a=f.next_action(owner,cid)
        assert a["action"] in {"ORGANIC_EXPERIMENT","BOOST_TOP_SIGNAL","GROW_AUDIENCE","RUN_NEXT_EXPERIMENT"}
        f.close()


def test_factory2_spend_limits_and_approval():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        f.fund(owner,100)
        f.settings(owner,{"daily_limit":20,"monthly_limit":50})
        pending=f.spend(owner,10,category="promotion",approved=False,note="test")
        assert pending["status"]=="PENDING_APPROVAL"
        assert float(f.dashboard(owner)["fund"]["balance"])==100
        assert f.dashboard(owner)["notifications"][0]["kind"]=="SPEND_APPROVAL_REQUIRED"
        committed=f.spend(owner,10,category="promotion",approved=True,note="test-approved")
        assert committed["status"]=="COMMITTED"
        assert float(committed["balance"])==90
        try:
            f.spend(owner,11,category="promotion",approved=True)
            assert False
        except ValueError as e:
            assert str(e)=="daily_spend_limit"
        f.close()


def test_factory2_attention_and_learning():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.record_signal(owner,cid,"engagement",0.2,confidence=0.8)
        decision=f.learn_from_signal(owner,cid)
        assert decision["decision"]=="change_hook"
        d=f.dashboard(owner)
        assert d["attention"]
        aid=d["attention"][0]["id"]
        assert f.resolve_attention(owner,aid) is True
        assert not f.dashboard(owner)["attention"]
        f.close()

def test_factory2_start_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        first=f.start(owner)
        second=f.start(owner)
        assert second["already_running"] is True
        assert second["job_id"]==first["job_id"]
        f.close()
