from __future__ import annotations

import io
import os
from hashlib import sha256

from .core import uid, now


class HFImageProvider:
    name = "huggingface-inference"
    connected = False

    def __init__(self, token=None, model=None, reference_model=None):
        self.token = token or os.getenv("HF_TOKEN")
        self.model = model or os.getenv("CHUMA_HF_MODEL", "black-forest-labs/FLUX.1-Krea-dev")
        self.reference_model = reference_model or os.getenv("CHUMA_HF_REFERENCE_MODEL", "Qwen/Qwen-Image-Edit")
        self.connected = bool(self.token)

    def generate(self, request: dict) -> dict:
        if not self.connected:
            raise RuntimeError("huggingface_token_not_configured")
        from huggingface_hub import InferenceClient

        brief = request.get("brief") or {}
        character = brief.get("character_name", "CHUMA")
        hook = brief.get("hook", "visual curiosity")
        mechanic = brief.get("mechanic", "identity discovery")
        dna = brief.get("character_dna") or {}
        identity = dna.get("identity") or dna.get("appearance") or dna.get("visual_dna") or {}
        behavior = dna.get("behavior") or dna.get("behavioral_dna") or {}
        dna_hint = ", ".join(str(v) for v in (identity.values() if isinstance(identity, dict) else []))
        behavior_hint = ", ".join(str(v) for v in (behavior.values() if isinstance(behavior, dict) else []))
        prompt = (
            f"Photorealistic adult human character named {character}. "
            f"Character identity must remain consistent and recognizable. "
            f"Identity DNA: {dna_hint}. Behavioral DNA: {behavior_hint}. "
            f"Content mechanic: {mechanic}. Hook: {hook}. "
            "Natural realistic skin, realistic anatomy, cinematic photography, "
            "high detail, editorial social-media portrait, no text, no watermark."
        )
        client = InferenceClient(provider="auto", api_key=self.token)
        reference_path = request.get("reference_image_path")
        reference_model = request.get("reference_model") or self.reference_model
        used_model = self.model
        if reference_path:
            used_model = reference_model
            with open(reference_path, "rb") as image_file:
                input_image = image_file.read()
            prompt = (
                f"Use the supplied reference image as the primary identity reference. "
                f"Preserve the same recognizable adult person, facial structure, hair, eye color, "
                f"skin characteristics and overall identity. Create a new photorealistic scene "
                f"for the requested content while keeping the person consistent. {prompt}"
            )
            image = client.image_to_image(
                input_image,
                prompt=prompt,
                model=reference_model,
            )
        else:
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
                "model": used_model,
                "request": request,
                "generated_at": now(),
            },
            "content_hash": sha256(data).hexdigest(),
            "bytes": data,
            "mime_type": "image/png",
        }
