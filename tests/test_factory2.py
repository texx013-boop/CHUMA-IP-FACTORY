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
