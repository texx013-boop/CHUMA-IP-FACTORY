def test_video_http_download_output_limit():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self, size=-1):
            return b"x" * (17 if size > 0 else 10)

    engine = HTTPVideoEngine("https://example.invalid", "token", max_output_bytes=16)
    payload = {"video_url": "https://cdn.invalid/video.mp4"}
    class ApiResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self, size=-1):
            return __import__("json").dumps(payload).encode()

    class FakeOpener:
        def open(self, request, timeout=None):
            return Response()

    def fake_urlopen(request, timeout=None):
        return ApiResponse()

    with patch.object(module, "_validate_external_http_url", side_effect=lambda url: url), \
         patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen), \
         patch.object(module.urllib.request, "build_opener", return_value=FakeOpener()):
        try:
            engine.render({"test": True})
            assert False, "oversized video output was accepted"
        except RuntimeError as exc:
            assert str(exc) == "video_provider_output_too_large"


def test_video_http_base64_output_limit():
    from unittest.mock import patch
    from chuma_ip_factory import video_combain as module

    class ApiResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self, size=-1):
            return __import__("json").dumps({"video_base64": "x" * 1000}).encode()