import tempfile
import os
import hashlib
import json
import time
from pathlib import Path
from chuma_ip_factory.global_factory_2 import Factory2, VERSION, ExternalProviderError

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


def test_factory2_auth_guard_locks_after_five_failures_and_resets_on_success():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        key="login:owner"
        assert f.auth_guard_check(key) is True
        for _ in range(5):
            f.auth_guard_failure(key)
        assert f.auth_guard_check(key) is False
        f.db.execute("UPDATE gf_auth_guard SET locked_until=? WHERE key=?",(0,key))
        f.commit()
        f.auth_guard_success(key)
        assert f.auth_guard_check(key) is True
        assert f.verify("owner","password123")==owner
        f.close()

def test_factory2_session_token_is_not_persisted_in_plaintext():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"factory.db"
        f=Factory2(db, Path(td)/"media")
        owner=f.create_owner("owner","password123")
        token=f.session(owner)
        stored=f.one("SELECT token FROM gf_sessions WHERE owner_id=?",(owner,))["token"]
        assert stored != token
        assert len(stored)==64
        assert f.owner_from_token(token)==owner
        assert f.owner_from_token("invalid-token") is None
        f.close()



def test_factory2_expired_session_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        token=f.session(owner)
        f.db.execute("UPDATE gf_sessions SET expires_at=? WHERE owner_id=?", (int(time.time())-1,owner))
        f.commit()
        assert f.owner_from_token(token) is None
        f.close()


def test_factory2_provider_contract_metadata_and_failure_is_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        adapter=f.distribution_adapter("unregistered")
        meta=adapter.metadata()
        assert meta["capabilities"]["publish"] is False
        assert meta["capabilities"]["measurement"] is False
        assert adapter.fetch_measurement if hasattr(adapter,"fetch_measurement") else False
        f.close()


def test_factory2_vk_official_adapter_uses_safe_secret_reference_and_real_api_contract():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        adapter=f.distribution_adapter("vk")
        meta=adapter.metadata()
        assert meta["mode"]=="official_api"
        assert meta["capabilities"]=={"publish":True,"measurement":True}
        ref="oauth://vk/test-account"
        env_name=adapter._secret_env_name(ref)
        os.environ[env_name]="test-token"
        calls=[]
        def fake_request(method, params, token):
            calls.append((method, params, token))
            if method=="wall.post":
                return {"post_id":123}
            return {"items":[{"views":{"count":100},"likes":{"count":7},"comments":{"count":2},"reposts":{"count":1}}]}
        adapter.request=fake_request
        published=adapter.publish({"account_id":"-42","credential_ref":ref,"text":"hello"})
        assert published["state"]=="PUBLISHED"
        assert published["external_id"]=="-42_123"
        measured=adapter.fetch_measurement({"external_id":"-42_123","credential_ref":ref})
        assert measured["views"]==100.0
        assert measured["likes"]==7.0
        assert measured["comments"]==2.0
        assert measured["shares"]==1.0
        assert calls[0][0]=="wall.post"
        assert calls[0][2]=="test-token"
        del os.environ[env_name]
        f.close()


def test_factory2_vk_provider_fails_closed_without_runtime_secret():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        adapter=f.distribution_adapter("vk")
        ref="oauth://vk/missing"
        try:
            adapter.publish({"account_id":"-42","credential_ref":ref,"text":"hello"})
            assert False
        except ExternalProviderError as exc:
            assert str(exc)=="credential_resolution_unavailable"
        f.close()


def test_factory2_distribution_requires_verified_artifact_before_provider_publish():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        eid=f.create_experiment(owner,cid,"artifact gate")
        f.set_compliance_rule(owner,"vk","publish","RU","GREEN",True,source="test",note="provider contract")
        f.connect_platform(owner,"vk",account_id="-42",credential_ref="oauth://vk/test")
        d=f.prepare_distribution(owner,"content-x","vk",experiment_id=eid)
        try:
            f.submit_distribution(owner,d["id"])
            assert False
        except ExternalProviderError as exc:
            assert str(exc)=="content_not_found"
        f.close()


def test_factory2_vk_image_sequence_uses_verified_artifact_and_attachment():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        eid=f.create_experiment(owner,cid,"vk image")
        f.set_compliance_rule(owner,"vk","publish","RU","GREEN",True,source="test",note="provider contract")
        f.connect_platform(owner,"vk",account_id="-42",credential_ref="oauth://vk/test")
        content_id="content-vk-image"
        f.chuma.store.db.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
            (content_id,owner,cid,json.dumps({"text":"hello VK"}), "READY",
             json.dumps({}),json.dumps({"test":True}),int(time.time()),int(time.time())))
        image=Path(td)/"verified.png"
        raw=b"\x89PNG\\r\\nverified-test-image"
        image.write_bytes(raw)
        digest=hashlib.sha256(raw).hexdigest()
        f.chuma.store.db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ART-vk",owner,cid,content_id,"ASSET-vk","4:5","image/png",
             str(image),digest,"test-provider","READY",int(time.time())))
        f.chuma.store.commit()
        d=f.prepare_distribution(owner,content_id,"vk",experiment_id=eid)
        assert d["state"]=="QUEUED"

        adapter=f.distribution_adapter("vk")
        ref="oauth://vk/test"
        env_name=adapter._secret_env_name(ref)
        os.environ[env_name]="test-token"
        calls=[]
        def fake_request(method, params, token):
            calls.append((method,dict(params),token))
            if method=="photos.getWallUploadServer":
                return {"upload_url":"https://upload.vk.com/vk","user_id":7}
            if method=="photos.saveWallPhoto":
                return [{"id":55,"owner_id":-42}]
            if method=="wall.post":
                assert params["attachments"]=="photo-42_55"
                return {"post_id":123}
            raise AssertionError(method)
        adapter.request=fake_request
        adapter.upload_multipart=lambda url,path,mime: {"server":1,"photo":"[]","hash":"upload-hash"}

        published=f.submit_distribution(owner,d["id"])
        assert published["state"]=="PUBLISHED"
        result=json.loads(published["result_json"])
        assert result["photo_id"]==55
        assert result["attachment"]=="photo-42_55"
        assert result["provenance"]["artifact_hash"]==digest
        assert [x[0] for x in calls]==[
            "photos.getWallUploadServer","photos.saveWallPhoto","wall.post"]
        assert all(x[2]=="test-token" for x in calls)
        del os.environ[env_name]
        f.close()


def test_factory2_vk_artifact_tamper_fails_before_provider_calls():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.set_compliance_rule(owner,"vk","publish","RU","GREEN",True,source="test",note="provider contract")
        f.connect_platform(owner,"vk",account_id="-42",credential_ref="oauth://vk/test")
        content_id="content-tampered"
        f.chuma.store.db.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
            (content_id,owner,cid,json.dumps({"text":"hello"}), "READY",
             json.dumps({}),json.dumps({"test":True}),int(time.time()),int(time.time())))
        image=Path(td)/"tampered.png"
        image.write_bytes(b"not-the-hash")
        f.chuma.store.db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ART-tamper",owner,cid,content_id,"ASSET-t","4:5","image/png",
             str(image),"0"*64,"test-provider","READY",int(time.time())))
        f.chuma.store.commit()
        d=f.prepare_distribution(owner,content_id,"vk")
        adapter=f.distribution_adapter("vk")
        adapter.request=lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called"))
        try:
            f.submit_distribution(owner,d["id"])
            assert False
        except ExternalProviderError as exc:
            assert str(exc)=="artifact_hash_mismatch"
        assert f.one("SELECT state FROM gf_distributions WHERE id=?",(d["id"],))["state"]=="FAILED"
        f.close()


def test_factory2_vk_missing_artifact_fails_closed_after_content_exists():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.set_compliance_rule(owner,"vk","publish","RU","GREEN",True,source="test",note="provider contract")
        f.connect_platform(owner,"vk",account_id="-42",credential_ref="oauth://vk/test")
        content_id="content-no-artifact"
        f.chuma.store.db.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
            (content_id,owner,cid,json.dumps({"text":"hello"}), "READY",
             json.dumps({}),json.dumps({"test":True}),int(time.time()),int(time.time())))
        f.chuma.store.commit()
        d=f.prepare_distribution(owner,content_id,"vk")
        try:
            f.submit_distribution(owner,d["id"])
            assert False
        except ExternalProviderError as exc:
            assert str(exc)=="content_artifact_missing"
        f.close()


def test_factory2_distribution_claim_prevents_second_submit_while_publishing():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db", Path(td)/"media")
        owner=f.create_owner("owner","password123")
        cid=f.bootstrap_character(owner,"Test IP")
        f.set_compliance_rule(owner,"vk","publish","RU","GREEN",True,source="test",note="provider contract")
        f.connect_platform(owner,"vk",account_id="-42",credential_ref="oauth://vk/test")
        content_id="content-claim"
        f.chuma.store.db.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
            (content_id,owner,cid,json.dumps({"text":"hello"}), "READY",
             json.dumps({}),json.dumps({"test":True}),int(time.time()),int(time.time())))
        f.chuma.store.commit()
        d=f.prepare_distribution(owner,content_id,"vk")
        f.db.execute("UPDATE gf_distributions SET state='PUBLISHING' WHERE id=?",(d["id"],))
        f.commit()
        result=f.submit_distribution(owner,d["id"])
        assert result["state"]=="PUBLISHING"
        f.close()


def test_factory2_http_body_rejects_non_object_json():
    from io import BytesIO
    from chuma_ip_factory.factory2_server import Handler
    h=object.__new__(Handler)
    h.headers={"Content-Length":"5"}
    h.rfile=BytesIO(b"[1,2]")
    try:
        h.body()
        assert False
    except ValueError as exc:
        assert str(exc)=="invalid_json"


def test_factory2_http_body_rejects_malformed_json():
    from io import BytesIO
    from chuma_ip_factory.factory2_server import Handler
    h=object.__new__(Handler)
    h.headers={"Content-Length":"3"}
    h.rfile=BytesIO(b"{x")
    try:
        h.body()
        assert False
    except ValueError as exc:
        assert str(exc)=="invalid_json"


def test_factory2_http_body_rejects_non_finite_json_constants():
    from io import BytesIO
    from chuma_ip_factory.factory2_server import Handler
    h=object.__new__(Handler); h.headers={"Content-Length":"3"}; h.rfile=BytesIO(b"NaN")
    try: h.body(); assert False
    except ValueError as exc: assert str(exc)=="invalid_json"

def test_factory2_http_owner_rejects_oversized_bearer_header():
    from chuma_ip_factory.factory2_server import Handler
    h=object.__new__(Handler); h.headers={"Authorization":"Bearer "+"x"*5000}; h.service=object()
    assert h.owner() is None

def test_factory2_vk_upload_url_must_be_https_vk_host():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db",Path(td)/"media"); a=f.distribution_adapter("vk")
        ref="oauth://vk/upload-test"; env=a._secret_env_name(ref); os.environ[env]="test-token"
        a.request=lambda *args,**kwargs: {"upload_url":"https://example.invalid/upload","user_id":7}
        p=Path(td)/"x.png"; p.write_bytes(b"x")
        try:
            a.publish({"account_id":"-42","credential_ref":ref,"text":"hello","artifact":{"storage_path":str(p),"content_hash":hashlib.sha256(b"x").hexdigest(),"status":"READY","mime_type":"image/png"}})
            assert False
        except ExternalProviderError as exc: assert str(exc)=="provider_upload_url_invalid"
        del os.environ[env]; f.close()

def test_factory2_spend_rejects_non_finite_amount():
    with tempfile.TemporaryDirectory() as td:
        f=Factory2(Path(td)/"factory.db",Path(td)/"media"); owner=f.create_owner("owner","password123"); f.fund(owner,100)
        for value in ("nan","inf","-inf"):
            try: f.spend(owner,value); assert False
            except ValueError as exc: assert str(exc)=="invalid_amount"
        f.close()


def test_factory2_vk_upload_disables_redirects(monkeypatch, tmp_path):
    import urllib.request
    adapter = __import__("chuma_ip_factory.global_factory_2", fromlist=["VKOfficialAdapter"]).VKOfficialAdapter("vk")
    image = tmp_path / "image.png"
    image.write_bytes(b"test-image")
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return b'{"server":1,"photo":"[]","hash":"ok"}'

    class Opener:
        def open(self, req, timeout):
            return Response()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    result = adapter.upload_multipart("https://upload.vk.com/upload", image, "image/png")
    redirect_handlers = [h for h in captured["handlers"] if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert any(issubclass(h, urllib.request.HTTPRedirectHandler) for h in redirect_handlers)
    handler_class = next(h for h in redirect_handlers if issubclass(h, urllib.request.HTTPRedirectHandler))
    assert handler_class().redirect_request(None, None, 302, "Found", {}, "https://attacker.example/upload") is None
    assert result["hash"] == "ok"


def test_factory2_vk_upload_rejects_oversized_response(monkeypatch, tmp_path):
    import urllib.request
    adapter = __import__("chuma_ip_factory.global_factory_2", fromlist=["VKOfficialAdapter"]).VKOfficialAdapter("vk")
    image = tmp_path / "image.png"
    image.write_bytes(b"test-image")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            assert limit == 1024 * 1024 + 1
            return b"x" * limit

    class Opener:
        def open(self, req, timeout):
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    try:
        adapter.upload_multipart("https://upload.vk.com/upload", image, "image/png")
        assert False, "oversized provider response must fail closed"
    except ExternalProviderError as exc:
        assert str(exc) == "provider_upload_response_too_large"
