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
