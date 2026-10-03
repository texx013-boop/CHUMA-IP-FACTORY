import pathlib
import tempfile

from chuma_ip_factory import CHUMA
from chuma_ip_factory.core import ImageProvider


class CaptureProvider(ImageProvider):
    name = "capture-image"
    connected = True

    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        data = b"reference-aware-test-image"
        import hashlib
        return {
            "asset_id": "ASSET-captured",
            "kind": "IMAGE",
            "status": "APPROVED",
            "meta": {"provider": self.name, "request": request},
            "content_hash": hashlib.sha256(data).hexdigest(),
            "bytes": data,
            "mime_type": "image/png",
        }


def test_reference_asset_is_passed_to_generation_and_not_used_as_production_asset():
    d = tempfile.TemporaryDirectory()
    provider = CaptureProvider()
    c = CHUMA(pathlib.Path(d.name) / "db.sqlite", pathlib.Path(d.name) / "media", image_provider=provider)
    owner = c.owner()
    cid = c.create_character(owner, "Леся")
    reference = b"fake-reference-image"
    attached = c.attach_reference(owner, cid, reference, "image/png", "lesya.png")

    c.initialize_character(owner, cid)

    generated = [r for r in provider.requests if r.get("reference_image_path")]
    assert len(generated) == 4
    assert all(pathlib.Path(r["reference_image_path"]).exists() for r in generated)
    assert all(r["reference_mode"] == "identity-preserving-image-to-image" for r in generated)

    content = c.create_content(owner, cid)
    row = c.store.one("SELECT production_json FROM content WHERE content_id=?", (content,))
    production = __import__("json").loads(row["production_json"])
    assert attached["asset_id"] not in production["asset_ids"]

    d.cleanup()
