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