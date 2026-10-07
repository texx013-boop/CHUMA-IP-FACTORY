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


def test_factory2_growth_step_uses_measured_fixture_and_not_placeholder():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.start(owner)
        result=f.run_growth_step(owner,cid)
        assert result["measurement"]["mode"]=="test_fixture"
        assert result["measurement"]["metrics"]["is_test_fixture"] is True
        assert result["learning"] is not None
        assert result["experiment_id"].startswith("EXP-")
        exp=f.one("SELECT status,result_json FROM gf_experiments WHERE id=?",(result["experiment_id"],))
        assert exp["status"]=="MEASURED"
        assert "measurement_mode" in exp["result_json"]
        sigs=f.all("SELECT kind,value,source FROM gf_signals WHERE owner_id=? AND content_id=?",(owner,result["content_id"]))
        assert sigs
        assert all(s["source"]=="test_fixture" for s in sigs)
        assert not any(float(s["value"])==0.0 and s["source"]=="awaiting_distribution" for s in sigs)
        f.close()

def test_factory2_learning_ignores_pending_distribution_signal():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.record_signal(owner,cid,"engagement",0.0,confidence=0.1,source="awaiting_distribution")
        assert f.learn_from_signal(owner,cid) is None
        f.record_signal(owner,cid,"engagement",0.8,confidence=0.8,source="test_fixture")
        decision=f.learn_from_signal(owner,cid)
        assert decision["decision"]=="continue_experiment"
        f.close()


def test_factory2_compliance_registry_is_fail_closed_and_expiring():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        initial=f.compliance_status("example-platform")
        assert initial["legal_class"]=="YELLOW"
        assert initial["automation_allowed"] is False
        assert f.connect_platform(owner,"example-platform")["status"]=="OWNER_REVIEW"
        rule=f.set_compliance_rule(owner,"example-platform","publish","RU","GREEN",True,source="owner_review",note="test rule")
        assert rule["legal_class"]=="GREEN"
        assert rule["automation_allowed"]==1
        assert f.connect_platform(owner,"example-platform",account_id="acct-1",credential_ref="secret-manager://example/account-1")["status"]=="READY"
        f.set_compliance_rule(owner,"example-platform","publish","RU","RED",False,source="owner_review",note="closed")
        assert f.connect_platform(owner,"example-platform")["status"]=="OWNER_REVIEW"
        f.close()


def test_factory2_experiment_lifecycle_and_idempotency():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.start(owner)
        first=f.create_experiment(owner,cid,"test","engagement")
        second=f.create_experiment(owner,cid,"different","engagement")
        assert first==second
        result=f.run_growth_step(owner,cid)
        exp=f.one("SELECT status FROM gf_experiments WHERE id=?",(first,))
        assert exp["status"]=="MEASURED"
        f.close()


def test_factory2_distribution_blocks_yellow_and_red_and_requires_auth():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        f.set_compliance_rule(owner,"yellow-platform","publish","RU","YELLOW",False,source="test",note="review")
        y=f.prepare_distribution(owner,"content-y","yellow-platform")
        assert y["state"]=="BLOCKED_COMPLIANCE"
        f.set_compliance_rule(owner,"red-platform","publish","RU","RED",False,source="test",note="closed")
        r=f.prepare_distribution(owner,"content-r","red-platform")
        assert r["state"]=="BLOCKED_COMPLIANCE"
        f.set_compliance_rule(owner,"green-platform","publish","RU","GREEN",True,source="test",note="allowed")
        f.connect_platform(owner,"green-platform")
        blocked=f.prepare_distribution(owner,"content-g","green-platform")
        assert blocked["state"]=="BLOCKED_AUTH"
        f.close()


def test_factory2_distribution_green_oauth_path_is_idempotent_and_password_free():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.set_compliance_rule(owner,"green-platform","publish","RU","GREEN",True,source="test",note="allowed")
        f.connect_platform(owner,"green-platform",account_id="acct-1",credential_ref="secret-manager://green/account-1")
        d=f.prepare_distribution(owner,"content-g","green-platform")
        assert d["state"]=="QUEUED"
        d2=f.prepare_distribution(owner,"content-g","green-platform")
        assert d2["id"]==d["id"]
        submitted=f.submit_distribution(owner,d["id"])
        assert submitted["state"]=="SUBMITTED"
        assert "password" not in str(dict(f.one("SELECT platform,status,connection_method,account_id,credential_ref,note FROM gf_platforms WHERE owner_id=?",(owner,)))).lower()
        f.close()


def test_factory2_external_measurement_never_uses_fixture_source():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.set_compliance_rule(owner,"green-platform","publish","RU","GREEN",True,source="test",note="allowed")
        f.connect_platform(owner,"green-platform",account_id="acct-1",credential_ref="secret-manager://green/account-1")
        d=f.prepare_distribution(owner,"content-m","green-platform",experiment_id=f.create_experiment(owner,cid,"external measurement"))
        f.db.execute("UPDATE gf_distributions SET state='PUBLISHED' WHERE id=?",(d["id"],))
        f.commit()
        measured=f.record_external_measurement(owner,d["id"],{"views":1000,"engagement":0.42},confidence=0.9)
        assert measured["measurement_mode"]=="external"
        sources=[x["source"] for x in f.all("SELECT source FROM gf_signals WHERE content_id=?",( "content-m",))]
        assert sources and all(x=="external" for x in sources)
        f.close()


def test_factory2_distribution_moves_experiment_to_measurement_then_learning():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        eid=f.create_experiment(owner,cid,"external hook")
        f.set_compliance_rule(owner,"green-platform","publish","RU","GREEN",True,source="test",note="allowed")
        f.connect_platform(owner,"green-platform",account_id="acct-1",credential_ref="secret-manager://green/account-1")
        d=f.prepare_distribution(owner,"content-state","green-platform",experiment_id=eid)
        submitted=f.submit_distribution(owner,d["id"])
        assert submitted["state"]=="SUBMITTED"
        assert f.one("SELECT status FROM gf_experiments WHERE id=?",(eid,))["status"]=="AWAITING_MEASUREMENT"
        f.db.execute("UPDATE gf_distributions SET state='PUBLISHED' WHERE id=?",(d["id"],))
        f.commit()
        m=f.record_external_measurement(owner,d["id"],{"engagement":0.7},confidence=0.9)
        assert m["measurement_mode"]=="external"
        assert f.one("SELECT status FROM gf_experiments WHERE id=?",(eid,))["status"]=="MEASURED"
        assert m["learning"] is not None
        f.close()


def test_factory2_ready_connection_rejects_raw_credential():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        f.set_compliance_rule(owner,"example-platform","publish","RU","GREEN",True,source="test",note="allowed")
        try:
            f.connect_platform(owner,"example-platform",account_id="acct-1",credential_ref="raw-token-value")
            assert False
        except ValueError as e:
            assert str(e)=="credential_ref_must_be_reference"
        f.close()


def test_factory2_unknown_provider_uses_safe_adapter_contract_only():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        adapter=f.distribution_adapter("not-registered")
        result=adapter.publish({"content_id":"x","credential_ref":"secret-manager://x"})
        assert result["mode"]=="adapter_stub"
        assert result["external_id"] is None
        assert result["state"]=="SUBMITTED"
        f.close()
