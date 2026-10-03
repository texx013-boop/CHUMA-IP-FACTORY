import socket

import pytest

from chuma_ip_factory.video_combain import HTTPVideoEngine, VideoCombain, _validate_external_http_url
from chuma_ip_factory.core import CHUMA
from pathlib import Path


def test_external_video_url_rejects_loopback():
    with pytest.raises(RuntimeError, match="video_provider_blocked_video_url"):
        _validate_external_http_url("http://127.0.0.1/video.mp4")


def test_external_video_url_rejects_private_network(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))],
    )
    with pytest.raises(RuntimeError, match="video_provider_blocked_video_url"):
        _validate_external_http_url("http://example.invalid/video.mp4")


def test_external_video_url_accepts_public_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
    )
    assert _validate_external_http_url("http://example.com/video.mp4") == "http://example.com/video.mp4"


def test_external_video_url_rejects_credentials():
    with pytest.raises(RuntimeError, match="video_provider_invalid_video_url"):
        _validate_external_http_url("https://user:pass@example.com/video.mp4")


def test_external_video_download_does_not_follow_redirects(monkeypatch):
    opened = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return b"video"

    class Opener:
        def open(self, request, timeout):
            opened["url"] = request.full_url
            opened["timeout"] = timeout
            return Response()

    def fake_build_opener(handler):
        opened["handler"] = handler
        return Opener()

    monkeypatch.setattr(
        "chuma_ip_factory.video_combain._validate_external_http_url",
        lambda url: url,
    )
    monkeypatch.setattr(
        "chuma_ip_factory.video_combain.urllib.request.build_opener",
        fake_build_opener,
    )

    engine = HTTPVideoEngine("https://provider.example/render", "secret", max_output_bytes=1024)
    monkeypatch.setattr(
        "chuma_ip_factory.video_combain.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download must use no-redirect opener")),
    )
    monkeypatch.setattr(
        engine,
        "endpoint",
        "https://provider.example/render",
    )

    class ProviderResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return b'{"video_url":"https://cdn.example/video.mp4"}'

    monkeypatch.setattr(
        "chuma_ip_factory.video_combain.urllib.request.urlopen",
        lambda *args, **kwargs: ProviderResponse(),
    )

    result = engine.render({"test": True})
    assert result["bytes"] == b"video"
    assert opened["url"] == "https://cdn.example/video.mp4"
    assert opened["handler"].__name__ == "_NoRedirect"


def test_video_job_failure_does_not_persist_internal_path_details():
    import tempfile

    d = tempfile.TemporaryDirectory()
    factory = CHUMA(Path(d.name) / "db.sqlite", Path(d.name) / "media")
    owner = factory.owner()
    character_id = factory.create_character(owner, "Failure Scope")
    video = VideoCombain(factory)

    class FailingEngine:
        name = "external-api"
        connected = True
        max_output_bytes = 1024

        def render(self, request):
            raise RuntimeError("/srv/private/provider-secret/path")

    video.engine = FailingEngine()
    job = video.create_job(owner, character_id, engine="external-api")
    try:
        with pytest.raises(RuntimeError):
            video.run_job(job["video_job_id"])
        stored = factory.store.one("SELECT error FROM video_jobs WHERE video_job_id=?", (job["video_job_id"],))
        assert stored["error"] == "video_job_failed"
        assert "/srv/private" not in stored["error"]
    finally:
        factory.store.close()
        d.cleanup()
