from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from typing import Any, Protocol

from .budget import BudgetPolicy, BudgetGuardProvider, PaidGenerationBlocked


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class VideoEngine(Protocol):
    name: str
    connected: bool

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


class ManifestVideoEngine:
    """Zero-cost contract engine used for tests and development."""

    name = "test-manifest"
    connected = True
    mode = "manifest"

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "manifest",
            "mime_type": "application/json",
            "bytes": json.dumps(
                {
                    "type": "shuma_video_render_manifest",
                    "version": 1,
                    "request": request,
                    "status": "READY_FOR_RENDER",
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        }


class HTTPVideoEngine:
    """Provider-neutral HTTP video renderer.

    Expected response: either video_base64 + optional mime_type, or video_url.
    The request always contains character/source provenance and the complete brief.
    """

    name = "external-api"
    mode = "api"

    def __init__(self, endpoint: str | None = None, api_key: str | None = None,
                 max_attempts: int = 2, timeout: int = 300, retry_delay: float = 1.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.max_attempts = max(1, int(max_attempts))
        self.timeout = max(1, int(timeout))
        self.retry_delay = max(0.0, float(retry_delay))
        self.connected = bool(endpoint and api_key)

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("video_provider_not_connected")
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                raw = payload.get("video_base64")
                if raw:
                    try:
                        data = base64.b64decode(raw, validate=True)
                    except Exception as exc:
                        raise RuntimeError("video_provider_invalid_base64") from exc
                    return {
                        "kind": "video",
                        "mime_type": payload.get("mime_type", "video/mp4"),
                        "bytes": data,
                        "provider_response": {"keys": sorted(payload.keys()), "attempt": attempt},
                    }
                url = payload.get("video_url")
                if url:
                    download_req = urllib.request.Request(
                        url, headers={"User-Agent": "SHUMA.SPACE/1.0"}
                    )
                    with urllib.request.urlopen(download_req, timeout=self.timeout) as response:
                        data = response.read()
                    return {
                        "kind": "video",
                        "mime_type": payload.get("mime_type", "video/mp4"),
                        "bytes": data,
                        "provider_response": {"keys": sorted(payload.keys()), "attempt": attempt},
                    }
                raise RuntimeError("video_provider_response_missing_video")
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code not in (429, 500, 502, 503, 504) or attempt >= self.max_attempts:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last = exc
                if attempt >= self.max_attempts:
                    raise
            if self.retry_delay:
                time.sleep(self.retry_delay * (2 ** (attempt - 1)))
        raise last or RuntimeError("video_provider_request_failed")


class VideoCombain:
    """Provider-neutral video production boundary for SHUMA.SPACE."""

    def __init__(self, factory, video_engine: VideoEngine | None = None,
                 budget_policy: BudgetPolicy | None = None):
        self.factory = factory
        self.store = factory.store
        self.root = Path(factory.asset_root) / "video"
        self.root.mkdir(parents=True, exist_ok=True)
        self.budget_policy = budget_policy or BudgetPolicy.from_env()
        self.engine = video_engine or ManifestVideoEngine()
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.execute(
            """CREATE TABLE IF NOT EXISTS video_jobs(
                video_job_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                character_id TEXT NOT NULL,
                source_content_id TEXT,
                source_asset_ids_json TEXT NOT NULL,
                brief_json TEXT NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL,
                output_artifact_id TEXT,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )"""
        )
        self.store.commit()

    def engines(self) -> list[dict[str, Any]]:
        external = self.engine if getattr(self.engine, "name", "") == "external-api" else None
        return [
            {
                "id": "test-manifest",
                "name": "Video Combain",
                "connected": True,
                "mode": "manifest",
                "description": "Проверочный движок контракта без платного видеорендера",
            },
            {
                "id": "external-api",
                "name": "External Video Engine",
                "connected": bool(external and getattr(external, "connected", False)),
                "mode": "api",
                "description": "Реальный видеорендер через внешний API",
            },
        ]

    def _selected_engine(self, engine_id: str):
        if engine_id == "test-manifest":
            return ManifestVideoEngine()
        if engine_id == "external-api":
            if getattr(self.engine, "name", "") != "external-api":
                raise RuntimeError("external_video_engine_not_configured")
            return self.engine
        raise ValueError("video_engine_not_supported")

    def create_job(
        self,
        owner_id: str,
        character_id: str,
        source_content_id: str | None = None,
        source_asset_ids: list[str] | None = None,
        brief: dict[str, Any] | None = None,
        engine: str = "test-manifest",
    ) -> dict[str, Any]:
        if not self.store.one(
            "SELECT character_id FROM characters WHERE character_id=? AND owner_id=?",
            (character_id, owner_id),
        ):
            raise ValueError("character_not_found")
        self._selected_engine(engine)

        job_id = _uid("VJOB")
        now = int(time.time())
        payload = {
            "format": "9:16",
            "duration_seconds": 8,
            "fps": 24,
            "style": "character-consistent",
            "source_content_id": source_content_id,
            "source_asset_ids": source_asset_ids or [],
            **(brief or {}),
        }
        self.store.db.execute(
            "INSERT INTO video_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id, owner_id, character_id, source_content_id,
                json.dumps(source_asset_ids or [], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False), engine, "QUEUED",
                None, None, now, now,
            ),
        )
        self.store.commit()
        return self.get_job(job_id)

    def run_job(self, video_job_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM video_jobs WHERE video_job_id=?", (video_job_id,))
        if not row:
            raise ValueError("video_job_not_found")
        if row["status"] == "SUCCEEDED":
            return self.get_job(video_job_id)

        now = int(time.time())
        self.store.db.execute(
            "UPDATE video_jobs SET status=?,updated_at=?,error=NULL WHERE video_job_id=?",
            ("RUNNING", now, video_job_id),
        )
        self.store.commit()

        try:
            brief = json.loads(row["brief_json"])
            source_assets = json.loads(row["source_asset_ids_json"])
            request = {
                "video_job_id": video_job_id,
                "owner_id": row["owner_id"],
                "character_id": row["character_id"],
                "source_content_id": row["source_content_id"],
                "source_asset_ids": source_assets,
                "brief": brief,
                "provenance": {
                    "character_id": row["character_id"],
                    "source_content_id": row["source_content_id"],
                    "source_asset_ids": source_assets,
                    "factory": "SHUMA.SPACE",
                },
            }
            engine = self._selected_engine(row["engine"])
            rendered = engine.render(request)
            data = rendered["bytes"]
            kind = rendered.get("kind", "video")
            mime_type = rendered.get("mime_type", "video/mp4")
            ext = "json" if kind == "manifest" else "mp4"
            artifact_id = _uid("VA")
            path = self.root / f"{video_job_id}.{ext}"
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.store.db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    artifact_id, row["owner_id"], row["character_id"],
                    row["source_content_id"], None,
                    "video" if kind == "video" else "video-manifest",
                    mime_type, str(path), digest,
                    getattr(engine, "name", row["engine"]), "READY", now,
                ),
            )
            self.store.db.execute(
                "UPDATE video_jobs SET status=?,output_artifact_id=?,updated_at=? WHERE video_job_id=?",
                ("SUCCEEDED", artifact_id, now, video_job_id),
            )
            self.store.commit()
            self.store.event(
                row["owner_id"], "VIDEO_JOB_COMPLETED", "video_job", video_job_id,
                {"artifact_id": artifact_id, "engine": row["engine"], "kind": kind},
            )
            return self.get_job(video_job_id)
        except (PaidGenerationBlocked, Exception) as exc:
            self.store.db.execute(
                "UPDATE video_jobs SET status=?,error=?,updated_at=? WHERE video_job_id=?",
                ("FAILED", str(exc), int(time.time()), video_job_id),
            )
            self.store.commit()
            raise

    def get_job(self, video_job_id: str):
        row = self.store.one("SELECT * FROM video_jobs WHERE video_job_id=?", (video_job_id,))
        if not row:
            return None
        result = dict(row)
        result["source_asset_ids"] = json.loads(result.pop("source_asset_ids_json"))
        result["brief"] = json.loads(result.pop("brief_json"))
        return result

    def list_jobs(self, owner_id: str, character_id: str | None = None):
        sql = "SELECT * FROM video_jobs WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if character_id:
            sql += " AND character_id=?"
            params.append(character_id)
        sql += " ORDER BY created_at DESC"
        return [self.get_job(r["video_job_id"]) for r in self.store.q(sql, tuple(params))]

    def status(self):
        return {
            "engines": self.engines(),
            "contract_version": 2,
            "budget": self.budget_policy.describe(),
        }
