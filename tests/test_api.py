import json
import threading
import urllib.request
import urllib.error
import tempfile
from pathlib import Path
from http.server import HTTPServer

from chuma_ip_factory.api import API
from chuma_ip_factory import CHUMA
from chuma_ip_factory.video_combain import VideoCombain


def test_http_health_and_auth_contract():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    previous_factory = API.factory
    previous_token = API.admin_token
    API.factory = factory
    API.admin_token = "test-admin-token"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            assert r.status == 200
            payload = json.loads(r.read().decode())
            assert payload["status"] == "ok"
            assert payload["version"] == "2.5.7"

        try:
            urllib.request.urlopen(base + "/provider", timeout=5)
            assert False, "protected endpoint accepted request without token"
        except urllib.error.HTTPError as e:
            assert e.code == 401

        req = urllib.request.Request(
            base + "/provider",
            headers={"Authorization": "Bearer test-admin-token"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
            payload = json.loads(r.read().decode())
            assert payload["name"] == "test-local-image"
            assert payload["connected"] is True

        owner_req = urllib.request.Request(
            base + "/owners",
            data=b"{}",
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(owner_req, timeout=5) as r:
            owner_id=json.loads(r.read().decode())["owner_id"]

        owners_req = urllib.request.Request(
            base + "/owners",
            headers={"Authorization": "Bearer test-admin-token", "X-Owner-ID": owner_id},
        )
        with urllib.request.urlopen(owners_req, timeout=5) as r:
            owners_payload=json.loads(r.read().decode())
            assert [o["owner_id"] for o in owners_payload["owners"]] == [owner_id]

        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    base + "/owners",
                    headers={"Authorization": "Bearer test-admin-token"},
                ),
                timeout=5,
            )
            assert False, "owner listing accepted without owner scope"
        except urllib.error.HTTPError as e:
            assert e.code == 403
        char_req = urllib.request.Request(
            base + "/characters",
            data=json.dumps({"owner_id":owner_id,"name":"Queue API"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json", "X-Owner-ID": owner_id},
        )
        with urllib.request.urlopen(char_req, timeout=5) as r:
            character_id=json.loads(r.read().decode())["character_id"]
        job_req = urllib.request.Request(
            base + "/jobs",
            data=json.dumps({"owner_id":owner_id,"character_id":character_id,"idempotency_key":"api-job-1"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json", "X-Owner-ID": owner_id},
        )
        with urllib.request.urlopen(job_req, timeout=5) as r:
            assert r.status == 202
            job_id=json.loads(r.read().decode())["job_id"]
        with urllib.request.urlopen(urllib.request.Request(base + "/jobs/"+job_id, headers={"Authorization":"Bearer test-admin-token","X-Owner-ID":owner_id}), timeout=5) as r:
            assert json.loads(r.read().decode())["status"] == "QUEUED"

        try:
            urllib.request.urlopen(base + "/artifacts/not-real", timeout=5)
            assert False, "artifact route accepted request without token"
        except urllib.error.HTTPError as e:
            assert e.code == 401

        oversized = urllib.request.Request(
            base + "/owners",
            data=b"x" * (API.MAX_BODY_BYTES + 1),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json", "X-Owner-ID": owner_id},
        )
        try:
            urllib.request.urlopen(oversized, timeout=5)
            assert False, "oversized request was accepted"
        except urllib.error.HTTPError as e:
            assert e.code == 413
    finally:
        server.shutdown()
        server.server_close()
        API.factory = previous_factory
        API.admin_token = previous_token
        factory.store.close()
        d.cleanup()



def test_owner_listing_is_scoped_to_request_owner():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    other = factory.owner()
    factory.create_character(owner, "Private")
    factory.create_character(other, "Other")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/owners",
            headers={"Authorization": "Bearer secret", "X-Owner-ID": owner},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert [item["owner_id"] for item in payload["owners"]] == [owner]
            assert payload["owners"][0]["characters"][0]["name"] == "Private"

        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/owners",
                    headers={"Authorization": "Bearer secret"},
                ),
                timeout=5,
            )
            assert False, "owner listing accepted without owner scope"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_artifact_download_rejects_tampered_bytes():
    import hashlib
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Integrity API")
    artifact_id = "ART-INTEGRITY"
    path = Path(d.name) / "media" / "artifact.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"original")
    now = int(__import__("time").time())
    factory.store.db.execute(
        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (artifact_id, owner, character_id, None, None, "test", "application/octet-stream",
         str(path), hashlib.sha256(b"original").hexdigest(), "test", "READY", now),
    )
    factory.store.commit()
    path.write_bytes(b"tampered")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/artifacts/{artifact_id}",
            headers={"Authorization": "Bearer secret", "X-Owner-ID": owner},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "tampered artifact was served"
        except urllib.error.HTTPError as exc:
            assert exc.code == 409
            payload = json.loads(exc.read().decode())
            assert payload["error"] == "artifact_integrity_failed"
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()

def test_artifact_download_enforces_owner_scope():
    import hashlib
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Scoped API")
    aid = "ART-SCOPE"; path = Path(d.name) / "media" / "scope.bin"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"private")
    factory.store.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, owner, cid, None, None, "test", "application/octet-stream", str(path), hashlib.sha256(b"private").hexdigest(), "test", "READY", int(__import__("time").time())))
    factory.store.commit()
    previous_factory, previous_token = API.factory, API.admin_token; API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API); threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/artifacts/{aid}", headers={"Authorization":"Bearer secret","X-Owner-ID":other})
        try: urllib.request.urlopen(req, timeout=5); assert False, "cross-owner artifact was served"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            assert json.loads(exc.read().decode())["error"] == "owner_forbidden"
    finally:
        server.shutdown(); server.server_close(); API.factory, API.admin_token = previous_factory, previous_token; factory.store.close(); d.cleanup()


def test_character_controls_voice_and_random_dna():
    import tempfile
    d=tempfile.TemporaryDirectory()
    factory=CHUMA(Path(d.name)/'db.sqlite',Path(d.name)/'media')
    owner=factory.owner(); cid=factory.create_character(owner,'Control Test')
    updated=factory.update_character_preferences(owner,cid,{'dna_notes':'спокойный, ироничный','voice':{'source':'synthetic','description':'низкий и спокойный'}})
    assert updated['card']['user_controls']['dna_notes']=='спокойный, ироничный'
    assert updated['card']['voice_profile']['source']=='synthetic'
    random=factory.randomize_character_dna(owner,cid,seed=42)
    assert random['card']['dna_mode']=='RANDOMIZED'
    assert len(random['card']['user_controls']['random_dna'])==5
    factory.store.close(); d.cleanup()


def test_user_voice_reference_is_persisted():
    import tempfile
    d=tempfile.TemporaryDirectory(); factory=CHUMA(Path(d.name)/'db.sqlite',Path(d.name)/'media'); owner=factory.owner(); cid=factory.create_character(owner,'Voice Test')
    r=factory.attach_voice(owner,cid,b'RIFF-test','audio/wav','my-voice.wav')
    p=factory.character_profile(owner,cid)
    assert p['card']['voice_profile']['source']=='user'; assert p['card']['voice_profile']['asset_id']==r['asset_id']
    factory.store.close(); d.cleanup()


def test_api_owner_scope_blocks_cross_owner_job_and_status():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Scoped Job")
    jid = factory.enqueue_job(owner, "AUTONOMOUS_CYCLE", {"character_id": cid, "platform": "local-test"}, "scope-job")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for path in (f"/jobs/{jid}", f"/status/{owner}"):
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                headers={"Authorization":"Bearer secret","X-Owner-ID":other},
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                assert False, f"cross-owner access accepted for {path}"
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
                assert json.loads(exc.read().decode())["error"] == "owner_forbidden"
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_api_binary_reference_and_voice_require_owner_scope():
    import tempfile
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Binary Scope")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for suffix, mime, payload in (("reference", "image/png", b"PNG-test"), ("voice", "audio/wav", b"RIFF-test")):
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/characters/{cid}/{suffix}",
                data=payload, method="POST",
                headers={"Authorization":"Bearer secret", "X-Owner-ID":other,
                         "Content-Type":mime, "X-Filename":f"test.{suffix}"},
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                assert False, f"cross-owner {suffix} upload accepted"
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
                assert json.loads(exc.read().decode())["error"] == "owner_forbidden"
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_api_character_profile_requires_matching_owner_scope():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Private Profile")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/characters/{cid}/profile",
            headers={"Authorization": "Bearer secret", "X-Owner-ID": other},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "cross-owner character profile was exposed"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            assert json.loads(exc.read().decode())["error"] == "owner_forbidden"
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_video_job_get_and_run_require_matching_owner_scope():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Private Video Job")
    job = VideoCombain(factory).create_job(owner, cid)
    previous_factory, previous_token, previous_video = API.factory, API.admin_token, getattr(API, 'video_combain', None)
    API.factory, API.admin_token, API.video_combain = factory, "secret", VideoCombain(factory)
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        for method, path, body in (
            ("GET", f"/video/jobs/{job['video_job_id']}", None),
            ("POST", f"/video/jobs/{job['video_job_id']}/run", b"{}"),
        ):
            req = urllib.request.Request(
                base + path,
                data=body,
                method=method,
                headers={"Authorization":"Bearer secret","X-Owner-ID":other,
                         "Content-Type":"application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                assert False, f"cross-owner video job {method} was accepted"
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
                assert json.loads(exc.read().decode())["error"] == "owner_forbidden"

        req = urllib.request.Request(
            base + f"/video/jobs/{job['video_job_id']}",
            headers={"Authorization":"Bearer secret","X-Owner-ID":owner},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert payload["video_job_id"] == job["video_job_id"]
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token, API.video_combain = previous_factory, previous_token, previous_video
        factory.store.close(); d.cleanup()


def test_video_job_listing_supports_owner_scoped_character_filter():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Filter A")
    other_cid = factory.create_character(other, "Filter B")
    job = VideoCombain(factory).create_job(owner, cid)
    previous_factory, previous_token, previous_video = API.factory, API.admin_token, getattr(API, 'video_combain', None)
    API.factory, API.admin_token, API.video_combain = factory, "secret", VideoCombain(factory)
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        req = urllib.request.Request(
            f"{base}/video/jobs?character_id={cid}",
            headers={"Authorization":"Bearer secret","X-Owner-ID":owner},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert [item["video_job_id"] for item in payload["jobs"]] == [job["video_job_id"]]

        req = urllib.request.Request(
            f"{base}/video/jobs?character_id={other_cid}",
            headers={"Authorization":"Bearer secret","X-Owner-ID":owner},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "foreign character filter was accepted"
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
            assert json.loads(exc.read().decode())["error"] == "character_not_found"
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token, API.video_combain = previous_factory, previous_token, previous_video
        factory.store.close(); d.cleanup()


def test_video_job_listing_is_scoped_to_owner():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Video Scoped")
    job = VideoCombain(factory).create_job(owner, cid)
    previous_factory, previous_token, previous_video = API.factory, API.admin_token, getattr(API, 'video_combain', None)
    API.factory, API.admin_token, API.video_combain = factory, "secret", VideoCombain(factory)
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/video/jobs",
            headers={"Authorization":"Bearer secret", "X-Owner-ID":other},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert payload["jobs"] == []
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/video/jobs",
            headers={"Authorization":"Bearer secret", "X-Owner-ID":owner},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert [item["video_job_id"] for item in payload["jobs"]] == [job["video_job_id"]]
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token, API.video_combain = previous_factory, previous_token, previous_video
        factory.store.close(); d.cleanup()



def test_video_status_is_safe_to_expose():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    previous_factory, previous_token, previous_video = API.factory, API.admin_token, getattr(API, "video_combain", None)
    API.factory, API.admin_token, API.video_combain = factory, "secret", VideoCombain(factory)
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/video/status",
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            encoded = json.dumps(payload, ensure_ascii=False).lower()
            assert "api_key" not in encoded
            assert "endpoint" not in encoded
            assert "authorization" not in encoded
            assert payload["contract_version"] == 2
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token, API.video_combain = previous_factory, previous_token, previous_video
        factory.store.close(); d.cleanup()



def test_video_job_get_ignores_query_string_without_changing_identity():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Query Job")
    factory.initialize_character(owner, character_id)
    video = VideoCombain(factory)
    job = video.create_job(owner, character_id)
    previous_factory, previous_token, previous_video = API.factory, API.admin_token, getattr(API, "video_combain", None)
    API.factory, API.admin_token, API.video_combain = factory, "secret", video
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/video/jobs/{job['video_job_id']}?view=compact", headers={"Authorization": "Bearer secret", "X-Owner-ID": owner})
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert payload["video_job_id"] == job["video_job_id"]
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token, API.video_combain = previous_factory, previous_token, previous_video
        factory.store.close(); d.cleanup()

def test_protected_diagnostics_require_authentication():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for path in ("/config", "/budget", "/video/status", "/provider"):
            try:
                urllib.request.urlopen(base + path, timeout=5)
                assert False, f"{path} accepted unauthenticated request"
            except urllib.error.HTTPError as exc:
                assert exc.code == 401

        req = urllib.request.Request(
            base + "/config",
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert payload["auth_required"] is True
            assert "admin_token" not in json.dumps(payload).lower()

        req = urllib.request.Request(
            base + "/budget",
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode())
            assert "api_key" not in json.dumps(payload).lower()
            assert "authorization" not in json.dumps(payload).lower()
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_api_rejects_invalid_json_without_internal_error_details():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/cycle",
            data=b"{not-json", method="POST",
            headers={"Authorization":"Bearer secret","Content-Type":"application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "invalid JSON was accepted"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode())
            assert payload == {"error":"invalid_json"}
            assert "traceback" not in json.dumps(payload).lower()
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()


def test_public_readiness_endpoints_remain_public():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    previous_factory, previous_token = API.factory, API.admin_token
    API.factory, API.admin_token = factory, "secret"
    server = HTTPServer(("127.0.0.1", 0), API)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for path in ("/health", "/ready"):
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=5) as response:
                assert response.status == 200
    finally:
        server.shutdown(); server.server_close()
        API.factory, API.admin_token = previous_factory, previous_token
        factory.store.close(); d.cleanup()
