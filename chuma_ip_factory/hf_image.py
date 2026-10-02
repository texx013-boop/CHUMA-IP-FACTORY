from __future__ import annotations

import io
import os
from hashlib import sha256

from .core import uid, now


class HFImageProvider:
    name = "huggingface-inference"
    connected = False

    def __init__(self, token=None, model=None):
        self.token = token or os.getenv("HF_TOKEN")
        self.model = model or os.getenv("CHUMA_HF_MODEL", "black-forest-labs/FLUX.1-Krea-dev")
        self.connected = bool(self.token)

    def generate(self, request: dict) -> dict:
        if not self.connected:
            raise RuntimeError("huggingface_token_not_configured")
        from huggingface_hub import InferenceClient

        brief = request.get("brief") or {}
        character = brief.get("character_name", "CHUMA")
        hook = brief.get("hook", "visual curiosity")
        mechanic = brief.get("mechanic", "identity discovery")
        prompt = (
            f"Photorealistic adult human character named {character}. "
            f"Character identity must remain consistent and recognizable. "
            f"Content mechanic: {mechanic}. Hook: {hook}. "
            "Natural realistic skin, realistic anatomy, cinematic photography, "
            "high detail, editorial social-media portrait, no text, no watermark."
        )
        client = InferenceClient(provider="auto", api_key=self.token)
        image = client.text_to_image(
            prompt,
            model=self.model,
            width=1024,
            height=1280,
        )
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data = buf.getvalue()
        return {
            "asset_id": uid("ASSET"),
            "kind": "IMAGE",
            "status": "APPROVED",
            "meta": {
                "provider": self.name,
                "model": self.model,
                "request": request,
                "generated_at": now(),
            },
            "content_hash": sha256(data).hexdigest(),
            "bytes": data,
            "mime_type": "image/png",
        }
