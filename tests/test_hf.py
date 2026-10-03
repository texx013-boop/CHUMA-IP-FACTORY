import io
import pathlib
import tempfile

from chuma_ip_factory.hf_image import HFImageProvider


class FakeImage:
    def save(self, buf, format="PNG"):
        buf.write(b"fake-png")


class FakeClient:
    last = None

    def __init__(self, *args, **kwargs):
        FakeClient.last = self
        self.image_to_image_calls = []
        self.text_to_image_calls = []

    def image_to_image(self, input_image, prompt, model):
        self.image_to_image_calls.append((input_image, prompt, model))
        return FakeImage()

    def text_to_image(self, prompt, model, width, height):
        self.text_to_image_calls.append((prompt, model, width, height))
        return FakeImage()


def test_hf_provider_uses_image_to_image_for_reference(monkeypatch):
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "InferenceClient", FakeClient)

    with tempfile.TemporaryDirectory() as d:
        ref = pathlib.Path(d) / "reference.png"
        ref.write_bytes(b"reference-bytes")

        provider = HFImageProvider(token="hf_test")
        result = provider.generate({
            "reference_image_path": str(ref),
            "brief": {
                "character_name": "Леся",
                "hook": "coffee",
                "mechanic": "identity",
            },
        })

        assert FakeClient.last.image_to_image_calls
        payload, prompt, model = FakeClient.last.image_to_image_calls[0]
        assert payload == b"reference-bytes"
        assert model == "Qwen/Qwen-Image-Edit"
        assert "reference image" in prompt
        assert result["mime_type"] == "image/png"
        assert result["meta"]["model"] == "Qwen/Qwen-Image-Edit"


def test_hf_provider_uses_text_to_image_without_reference(monkeypatch):
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "InferenceClient", FakeClient)

    provider = HFImageProvider(token="hf_test")
    provider.generate({
        "brief": {
            "character_name": "Леся",
            "hook": "portrait",
            "mechanic": "identity",
        },
    })

    calls = FakeClient.last.text_to_image_calls
    assert len(calls) == 1
    assert calls[0][1:] == ("black-forest-labs/FLUX.1-Krea-dev", 1024, 1280)
