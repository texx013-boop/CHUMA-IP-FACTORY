import json
import threading
import urllib.request
import urllib.error
import tempfile
from pathlib import Path
from http.server import HTTPServer

from chuma_ip_factory.api import API
from chuma_ip_factory import CHUMA


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
            assert payload["version"] == "2.5.3"

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
        char_req = urllib.request.Request(
            base + "/characters",
            data=json.dumps({"owner_id":owner_id,"name":"Queue API"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(char_req, timeout=5) as r:
            character_id=json.loads(r.read().decode())["character_id"]
        job_req = urllib.request.Request(
            base + "/jobs",
            data=json.dumps({"owner_id":owner_id,"character_id":character_id,"idempotency_key":"api-job-1"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(job_req, timeout=5) as r:
            assert r.status == 202
            job_id=json.loads(r.read().decode())["job_id"]
        with urllib.request.urlopen(urllib.request.Request(base + "/jobs/"+job_id, headers={"Authorization":"Bearer test-admin-token"}), timeout=5) as r:
            assert json.loads(r.read().decode())["status"] == "QUEUED"

        oversized = urllib.request.Request(
            base + "/owners",
            data=b"x" * (API.MAX_BODY_BYTES + 1),
            method="POST",
            headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json"},
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
