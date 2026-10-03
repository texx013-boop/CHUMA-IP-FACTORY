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
    video = VideoCombain(factory)

    status = video.status()
    assert status["contract_version"] == 2
    assert status["budget"]["mode"] == "free"
    assert any(e["id"] == "test-manifest" and e["connected"] for e in status["engines"])

    job = video.create_job(
        owner,
        character_id,
        source_content_id="CONTENT-1",
        source_asset_ids=["ASSET-1", "ASSET-2"],
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
    assert artifact["character_id"] == character_id
    assert artifact["content_id"] == "CONTENT-1"
    assert artifact["provider"] == "test-manifest"
    assert artifact["variant"] == "video-manifest"

    listed = video.list_jobs(owner, character_id)
    assert listed and listed[0]["video_job_id"] == done["video_job_id"]

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
