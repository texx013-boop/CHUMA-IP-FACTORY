import json
import tempfile
from pathlib import Path

from chuma_ip_factory import CHUMA
from chuma_ip_factory.video_combain import HTTPVideoEngine, VideoCombain
from chuma_ip_factory.budget import BudgetGuardProvider, BudgetPolicy, PaidGenerationBlocked


def test_video_combain_manifest_job_and_provenance():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Video Test")
    factory.initialize_character(owner, character_id)
    content_id = factory.create_content(owner, character_id)
    factory.qc(owner, content_id)
    artifacts = factory.store.q("SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? AND status='READY'", (owner, content_id))
    assert artifacts
    video = VideoCombain(factory)

    status = video.status()
    assert status["contract_version"] == 2
    assert status["budget"]["mode"] == "free"
    assert any(e["id"] == "test-manifest" and e["connected"] for e in status["engines"])

    job = video.create_job(
        owner,
        character_id,
        source_content_id=content_id,
        source_asset_ids=[a["artifact_id"] for a in artifacts],
        brief={"hook": "camera turns toward character"},
    )
    assert job["status"] == "QUEUED"

    done = video.run_job(job["video_job_id"])
    assert done["status"] == "SUCCEEDED"
    assert done["output_artifact_id"]

    artifact = factory.store.one(
        "SELECT * FROM artifacts WHERE artifact_id=?",
        (done["output_artifact_id"],),
    )
    assert artifact["owner_id"] == owner
    assert artifact["character_id"] == character_id
    assert artifact["content_id"] == "CONTENT-1"
    assert artifact["provider"] == "test-manifest"
    assert artifact["variant"] == "video-manifest"

    listed = video.list_jobs(owner, character_id)
    assert listed and listed[0]["video_job_id"] == done["video_job_id"]

    factory.store.close()
    d.cleanup()


def test_video_combain_does_not_double_claim_running_job():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Claim Test")
    video = VideoCombain(factory)
    job = video.create_job(owner, character_id)
    factory.store.db.execute(
        "UPDATE video_jobs SET status='RUNNING' WHERE video_job_id=?",
        (job["video_job_id"],),
    )
    factory.store.commit()
    current = video.run_job(job["video_job_id"])
    assert current["status"] == "RUNNING"
    factory.store.close()
    d.cleanup()


def test_video_combain_is_idempotent_after_success():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Video Idempotent")
    video = VideoCombain(factory)

    job = video.create_job(owner, character_id)
    first = video.run_job(job["video_job_id"])
    second = video.run_job(job["video_job_id"])
    assert second["status"] == "SUCCEEDED"
    assert second["output_artifact_id"] == first["output_artifact_id"]

    factory.store.close()
    d.cleanup()

def test_external_video_engine_requires_configuration():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "External Test")
    video = VideoCombain(factory, video_engine=HTTPVideoEngine(), budget_policy=BudgetPolicy())
    assert video.status()["engines"][1]["connected"] is False
    try:
        video.create_job(owner, character_id, engine="external-api")
        assert False, "unconfigured external engine was accepted"
    except RuntimeError as exc:
        assert str(exc) == "external_video_engine_not_configured"
    factory.store.close()
    d.cleanup()


def test_paid_video_generation_is_blocked_in_free_mode():
    class Dummy:
        name = "external-api"
        connected = True
        def generate(self, request):
            raise AssertionError("renderer must not be called")

    guarded = BudgetGuardProvider(Dummy(), BudgetPolicy(mode="free", allow_paid=False), "metered")
    assert guarded.connected is False
    try:
        guarded.generate({})
        assert False, "metered generation was not blocked"
    except PaidGenerationBlocked:
        pass

def test_video_combain_can_build_job_from_latest_ready_image_content():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Content Source")
    content_id = "CONTENT-READY"
    asset_id = "ASSET-READY"
    artifact_id = "ART-READY"
    source = Path(d.name) / "media" / "source.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"{}")
    digest = __import__("hashlib").sha256(b"{}").hexdigest()
    now = __import__("time").time_ns() // 1_000_000_000
    factory.store.db.execute(
        "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?)",
        (content_id, owner, character_id, "{}", "READY",
         __import__("json").dumps({"asset_ids": [asset_id]}),
         __import__("json").dumps({"character_id": character_id, "asset_ids": [asset_id]}),
         now, now),
    )
    factory.store.db.execute(
        "INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)",
        (asset_id, owner, character_id, "TARGETED", "APPROVED", "{}", digest, now),
    )
    factory.store.db.execute(
        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (artifact_id, owner, character_id, content_id, asset_id, "9:16",
         "application/json", str(source), digest, "test-manifest", "READY", now),
    )
    factory.store.commit()
    video = VideoCombain(factory)
    job = video.create_job_from_latest_content(owner, character_id)
    assert job["source_content_id"] == content_id
    assert job["source_asset_ids"] == [artifact_id]
    done = video.run_job(job["video_job_id"])
    assert done["status"] == "SUCCEEDED"
    factory.store.close()
    d.cleanup()


def test_video_http_rejects_non_http_download_url():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class ApiResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self, size=-1):
            return __import__("json").dumps({"video_url": "file:///tmp/video.mp4"}).encode()

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    with patch.object(module.urllib.request, "urlopen", return_value=ApiResponse()) as mocked:
        try:
            engine.render({"test": True})
            assert False, "non-http video URL was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_invalid_video_url"
        mocked.assert_called_once()


def test_video_http_rejects_embedded_credentials_in_download_url():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class ApiResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self, size=-1):
            return __import__("json").dumps({"video_url": "https://user:pass@example.invalid/video.mp4"}).encode()

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    with patch.object(module.urllib.request, "urlopen", return_value=ApiResponse()) as mocked:
        try:
            engine.render({"test": True})
            assert False, "credential-bearing video URL was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_invalid_video_url"
        mocked.assert_called_once()


def test_video_http_download_output_limit():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self, size=-1):
            return b"x" * (size if size > 0 else 10)

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    payload = {"video_url": "https://cdn.invalid/video.mp4"}
    class ApiResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return __import__("json").dumps(payload).encode()

    with patch.object(module.urllib.request, "urlopen", side_effect=[ApiResponse(), Response()]):
        try:
            engine.render({"test": True})
            assert False, "oversized video output was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_output_too_large"


def test_video_http_base64_output_limit():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class ApiResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self):
            return __import__("json").dumps({"video_base64": "x" * 1000}).encode()

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    with patch.object(module.urllib.request, "urlopen", return_value=ApiResponse()):
        try:
            engine.render({"test": True})
            assert False, "oversized base64 output was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_output_too_large"


def test_video_http_provider_response_limit():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class ApiResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self, size=-1):
            return b"x" * (size if size > 0 else 10)

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    with patch.object(module.urllib.request, "urlopen", return_value=ApiResponse()):
        try:
            engine.render({"test": True})
            assert False, "oversized provider response was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_response_too_large"


def test_video_combain_jobs_survive_restart():
    d = tempfile.TemporaryDirectory()
    db = Path(d.name) / "db.sqlite"
    media = Path(d.name) / "media"
    factory = CHUMA(db, media)
    owner = factory.owner()
    character_id = factory.create_character(owner, "Restart Video")
    factory.initialize_character(owner, character_id)
    content_id = factory.create_content(owner, character_id)
    factory.qc(owner, content_id)
    artifacts = factory.store.q("SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? AND status='READY'", (owner, content_id))
    assert artifacts
    video = VideoCombain(factory)
    job = video.create_job(owner, character_id, source_content_id=content_id,
                           source_asset_ids=[artifacts[0]["artifact_id"]], brief={"hook": "persist"})
    job_id = job["video_job_id"]
    factory.store.close()

    reopened = CHUMA(db, media)
    reopened_video = VideoCombain(reopened)
    restored = reopened_video.get_job(job_id)
    assert restored is not None
    assert restored["owner_id"] == owner
    assert restored["character_id"] == character_id
    assert restored["source_content_id"] == content_id
    assert restored["source_asset_ids"] == [artifacts[0]["artifact_id"]]
    assert restored["brief"]["hook"] == "persist"
    reopened.store.close()
    d.cleanup()


def test_video_combain_idempotency_lookup_index_is_created():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    VideoCombain(factory)
    indexes = factory.store.q("PRAGMA index_list('video_jobs')")
    assert any(row["name"] == "idx_video_jobs_source_dedupe" for row in indexes)
    factory.store.close()
    d.cleanup()


def test_video_combain_idempotency_uses_source_content_and_brief():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Dedup")
    factory.initialize_character(owner, character_id)
    content_id = factory.create_content(owner, character_id)
    factory.qc(owner, content_id)
    video = VideoCombain(factory)
    a = video.create_job_from_content(owner, content_id, {"hook": "same"})
    b = video.create_job_from_content(owner, content_id, {"hook": "same"})
    c = video.create_job_from_content(owner, content_id, {"hook": "different"})
    assert a["video_job_id"] == b["video_job_id"]
    assert a["video_job_id"] != c["video_job_id"]
    factory.store.close()
    d.cleanup()


def test_video_combain_artifact_is_atomically_written_and_has_expected_digest():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Atomic Video")
    video = VideoCombain(factory)

    job = video.create_job(owner, character_id, brief={"hook": "atomic"})
    done = video.run_job(job["video_job_id"])
    artifact = factory.store.one(
        "SELECT storage_path,content_hash,status FROM artifacts WHERE artifact_id=?",
        (done["output_artifact_id"],),
    )
    output = Path(artifact["storage_path"])
    assert artifact["status"] == "READY"
    assert output.exists()
    assert not output.with_suffix(output.suffix + ".tmp").exists()
    assert artifact["content_hash"] == hashlib.sha256(output.read_bytes()).hexdigest()

    factory.store.close()
    d.cleanup()


def test_video_combain_revalidates_provenance_before_render():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Queued Provenance")
    factory.initialize_character(owner, character_id)
    content_id = factory.create_content(owner, character_id)
    factory.qc(owner, content_id)
    artifact = factory.store.one(
        "SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? AND status='READY' LIMIT 1",
        (owner, content_id),
    )
    video = VideoCombain(factory)
    job = video.create_job(
        owner, character_id,
        source_content_id=content_id,
        source_asset_ids=[artifact["artifact_id"]],
    )

    factory.store.db.execute(
        "UPDATE artifacts SET status='REJECTED' WHERE artifact_id=?",
        (artifact["artifact_id"],),
    )
    factory.store.commit()

    try:
        video.run_job(job["video_job_id"])
        assert False, "stale queued provenance was rendered"
    except RuntimeError as exc:
        assert str(exc) == "source_asset_forbidden"

    failed = video.get_job(job["video_job_id"])
    assert failed["status"] == "FAILED"
    assert failed["error"] == "source_asset_forbidden"
    factory.store.close()
    d.cleanup()


def test_video_combain_rejects_tampered_source_artifact_before_render():
    import hashlib

    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Tampered Source")
    factory.initialize_character(owner, character_id)
    content_id = factory.create_content(owner, character_id)
    factory.qc(owner, content_id)
    artifact = factory.store.one(
        "SELECT artifact_id,storage_path,content_hash FROM artifacts "
        "WHERE owner_id=? AND content_id=? AND status='READY' LIMIT 1",
        (owner, content_id),
    )
    video = VideoCombain(factory)
    job = video.create_job(
        owner, character_id,
        source_content_id=content_id,
        source_asset_ids=[artifact["artifact_id"]],
    )

    path = Path(artifact["storage_path"])
    path.write_bytes(b"tampered-source")

    try:
        video.run_job(job["video_job_id"])
        assert False, "tampered source artifact was rendered"
    except RuntimeError as exc:
        assert str(exc) == "source_asset_integrity_failed"

    failed = video.get_job(job["video_job_id"])
    assert failed["status"] == "FAILED"
    assert failed["error"] == "source_asset_integrity_failed"
    factory.store.close()
    d.cleanup()


def test_video_combain_rejects_foreign_provenance_inputs():
    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner(); other = factory.owner()
    cid = factory.create_character(owner, "Provenance Owner")
    other_cid = factory.create_character(other, "Other Owner")
    factory.initialize_character(owner, cid)
    content_id = factory.create_content(owner, cid)
    factory.qc(owner, content_id)
    artifact = factory.store.one("SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? AND status='READY' LIMIT 1", (owner, content_id))
    try:
        VideoCombain(factory).create_job(other, other_cid, source_content_id=content_id, source_asset_ids=[artifact["artifact_id"]])
        assert False, "foreign provenance was accepted"
    except ValueError as exc:
        assert str(exc) == "content_not_found"
    factory.store.close()
    d.cleanup()
