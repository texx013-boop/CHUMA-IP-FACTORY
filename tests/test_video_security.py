import socket

import pytest

from chuma_ip_factory.video_combain import _validate_external_http_url


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
