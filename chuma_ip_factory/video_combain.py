from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Protocol

from .budget import BudgetPolicy, PaidGenerationBlocked


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class VideoEngine(Protocol):
    name: str
    connected: bool

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


class ManifestVideoEngine:
    name = "test-manifest"
    connected = True
    mode = "manifest"

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "manifest",
            "mime_type": "application/json",
            "bytes": json.dumps(
                {"type": "shuma_video_render_manifest", "version": 1,
                 "request": request, "status": "READY_FOR_RENDER"},
                ensure_ascii=False, indent=2).encode("utf-8"),
        }


class HTTPVideoEngine:
    name = "external-api"
    mode = "api"

    def __init__(self, endpoint: str | None = None, api_key: str | None = None,
                 max_attempts: int = 2, timeout: int = 300, retry_delay: float = 1.0,
                 max_output_bytes: int = 256 * 1024 * 1024):
        self.endpoint = endpoint
        self.api_key = api_key
        self.max_attempts = max(1, int(max_attempts))
        self.timeout = max(1, int(timeout))
        self.retry_delay = max(0.0, float(retry_delay))
        self.max_output_bytes = max(1, int(max_output_bytes))
        self.max_response_bytes = max(self.max_output_bytes + 1024 * 1024, int(self.max_output_bytes * 1.5) + 65536)
        self.connected = bool(endpoint and api_key)

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("video_provider_not_connected")
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    response_data = response.read(self.max_response_bytes + 1)
                if len(response_data) > self.max_response_bytes:
                    raise RuntimeError("video_provider_response_too_large")
                payload = json.loads(response_data.decode("utf-8"))
                raw = payload.get("video_base64")
                if raw:
                    if not isinstance(raw, str) or len(raw) > ((self.max_output_bytes + 2) // 3) * 4:
                        raise RuntimeError("video_provider_output_too_large")
                    try:
                        data = base64.b64decode(raw, validate=True)
                    except Exception as exc:
                        raise RuntimeError("video_provider_invalid_base64") from exc
                    return {"kind": "video", "mime_type": payload.get("mime_type", "video/mp4"),
                            "bytes": data,
                            "provider_response": {"keys": sorted(payload.keys()), "attempt": attempt}}
                url = payload.get("video_url")
                if url:
                    parsed_url = urllib.parse.urlparse(url)
                    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                        raise RuntimeError("video_provider_invalid_video_url")
                    if parsed_url.username or parsed_url.password:
                        raise RuntimeError("video_provider_invalid_video_url")
                    download_req = urllib.request.Request(url, headers={"User-Agent": "SHUMA.SPACE/1.0"})
                    with urllib.request.urlopen(download_req, timeout=self.timeout) as response:
                        data = response.read(self.max_output_bytes + 1)
                    if len(data) > self.max_output_bytes:
                        raise RuntimeError("video_provider_output_too_large")
                    return {"kind": "video", "mime_type": payload.get("mime_type", "video/mp4"),
                            "bytes": data,
                            "provider_response": {"keys": sorted(payload.keys()), "attempt": attempt}}
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


class BudgetVideoEngine:
    def __init__(self, provider: VideoEngine, policy: BudgetPolicy, cost_class: str = "metered"):
        self.provider = provider
        self.policy = policy
        self.cost_class = cost_class
        self.name = getattr(provider, "name", "unknown")
        self.connected = bool(getattr(provider, "connected", False)) and policy.allows(cost_class)

    def render(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.policy.allows(self.cost_class):
            raise PaidGenerationBlocked("paid_generation_blocked_by_budget_policy")
        return self.provider.render(request)


class VideoCombain:
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
                video_job_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                character_id TEXT NOT NULL, source_content_id TEXT,
                source_asset_ids_json TEXT NOT NULL, brief_json TEXT NOT NULL,
                engine TEXT NOT NULL, status TEXT NOT NULL,
                output_artifact_id TEXT, error TEXT,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")
        self.store.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_jobs_source_dedupe "
            "ON video_jobs(owner_id, character_id, engine, source_content_id, brief_json, status, created_at)"
        )
        self.store.commit()

    def engines(self) -> list[dict[str, Any]]:
        external = self.engine if getattr(self.engine, "name", "") == "external-api" else None
        return [
            {"id": "test-manifest", "name": "Video Combain", "connected": True,
             "mode": "manifest", "description": "Проверочный движок без платного видеорендера"},
            {"id": "external-api", "name": "External Video Engine",
             "connected": bool(external and getattr(external, "connected", False)),
             "mode": "api", "description": "Реальный видеорендер через внешний API"},
        ]

    def _selected_engine(self, engine_id: str):
        if engine_id == "test-manifest":
            return ManifestVideoEngine()
        if engine_id == "external-api":
            if getattr(self.engine, "name", "") != "external-api" or not getattr(self.engine, "connected", False):
                raise RuntimeError("external_video_engine_not_configured")
            return self.engine
        raise ValueError("video_engine_not_supported")

    def create_job(self, owner_id: str, character_id: str,
                   source_content_id: str | None = None,
                   source_asset_ids: list[str] | None = None,
                   brief: dict[str, Any] | None = None,
                   engine: str = "test-manifest") -> dict[str, Any]:
        if not self.store.one("SELECT character_id FROM characters WHERE character_id=? AND owner_id=?",
                              (character_id, owner_id)):
            raise ValueError("character_not_found")
        self._selected_engine(engine)
        if source_content_id:
            content_row = self.store.one(
                "SELECT character_id FROM content WHERE content_id=? AND owner_id=?",
                (source_content_id, owner_id),
            )
            if not content_row or content_row["character_id"] != character_id:
                raise ValueError("content_not_found")
        asset_ids = list(source_asset_ids or [])
        if asset_ids:
            placeholders = ",".join("?" for _ in asset_ids)
            rows = self.store.q(
                f"SELECT artifact_id,owner_id,character_id,content_id,status FROM artifacts "
                f"WHERE artifact_id IN ({placeholders})",
                tuple(asset_ids),
            )
            by_id = {r["artifact_id"]: r for r in rows}
            if len(by_id) != len(set(asset_ids)):
                raise ValueError("source_asset_not_found")
            for aid in asset_ids:
                r = by_id[aid]
                if r["owner_id"] != owner_id or r["character_id"] != character_id or r["status"] != "READY":
                    raise ValueError("source_asset_forbidden")
                if source_content_id and r["content_id"] != source_content_id:
                    raise ValueError("source_asset_mismatch")
        job_id = _uid("VJOB")
        now = int(time.time())
        payload = {"format": "9:16", "duration_seconds": 8, "fps": 24,
                   "style": "character-consistent", "source_content_id": source_content_id,
                   "source_asset_ids": asset_ids, **(brief or {})}
        brief_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        # Image-content jobs are idempotent: repeated factory triggers reuse the
        # active/successful job for the same source, engine and rendering brief.
        if source_content_id:
            existing = self.store.one(
                "SELECT video_job_id FROM video_jobs "
                "WHERE owner_id=? AND character_id=? AND engine=? "
                "AND source_content_id=? AND brief_json=? "
                "AND status IN ('QUEUED','RUNNING','SUCCEEDED') "
                "ORDER BY created_at DESC LIMIT 1",
                (owner_id, character_id, engine, source_content_id, brief_json),
            )
            if existing:
                return self.get_job(existing["video_job_id"])
        self.store.db.execute(
            "INSERT INTO video_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, owner_id, character_id, source_content_id,
             json.dumps(asset_ids, ensure_ascii=False),
             brief_json, engine, "QUEUED", None, None, now, now))
        self.store.commit()
        return self.get_job(job_id)

    def _validate_job_provenance(self, row, source_assets: list[str]) -> None:
        """Re-check queued provenance immediately before an external render."""
        owner_id = row["owner_id"]
        character_id = row["character_id"]
        if not self.store.one(
            "SELECT character_id FROM characters WHERE character_id=? AND owner_id=?",
            (character_id, owner_id),
        ):
            raise RuntimeError("character_not_found")
        source_content_id = row["source_content_id"]
        if source_content_id:
            content_row = self.store.one(
                "SELECT character_id FROM content WHERE content_id=? AND owner_id=?",
                (source_content_id, owner_id),
            )
            if not content_row or content_row["character_id"] != character_id:
                raise RuntimeError("content_not_found")
        asset_ids = list(source_assets or [])
        if not asset_ids:
            return
        placeholders = ",".join("?" for _ in asset_ids)
        rows = self.store.q(
            f"SELECT artifact_id,owner_id,character_id,content_id,status FROM artifacts "
            f"WHERE artifact_id IN ({placeholders})",
            tuple(asset_ids),
        )
        by_id = {r["artifact_id"]: r for r in rows}
        if len(by_id) != len(set(asset_ids)):
            raise RuntimeError("source_asset_not_found")
        for aid in asset_ids:
            r = by_id[aid]
            if r["owner_id"] != owner_id or r["character_id"] != character_id or r["status"] != "READY":
                raise RuntimeError("source_asset_forbidden")
            if source_content_id and r["content_id"] != source_content_id:
                raise RuntimeError("source_asset_mismatch")

    def run_job(self, video_job_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM video_jobs WHERE video_job_id=?", (video_job_id,))
        if not row:
            raise ValueError("video_job_not_found")
        if row["status"] == "SUCCEEDED":
            return self.get_job(video_job_id)
        now = int(time.time())
        self.store.db.execute("UPDATE video_jobs SET status=?,updated_at=?,error=NULL WHERE video_job_id=?",
                              ("RUNNING", now, video_job_id))
        self.store.commit()
        try:
            brief = json.loads(row["brief_json"])
            source_assets = json.loads(row["source_asset_ids_json"])
            self._validate_job_provenance(row, source_assets)
            request = {
                "video_job_id": video_job_id, "owner_id": row["owner_id"],
                "character_id": row["character_id"], "source_content_id": row["source_content_id"],
                "source_asset_ids": source_assets, "brief": brief,
                "provenance": {"character_id": row["character_id"],
                               "source_content_id": row["source_content_id"],
                               "source_asset_ids": source_assets, "factory": "SHUMA.SPACE"}}
            engine = self._selected_engine(row["engine"])
            rendered = engine.render(request)
            data = rendered["bytes"]
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise RuntimeError("video_provider_empty_output")
            if len(data) > getattr(engine, "max_output_bytes", 256 * 1024 * 1024):
                raise RuntimeError("video_provider_output_too_large")
            kind = rendered.get("kind", "video")
            mime_type = rendered.get("mime_type", "video/mp4")
            ext = "json" if kind == "manifest" else "mp4"
            artifact_id = _uid("VA")
            path = self.root / f"{video_job_id}.{ext}"
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            try:
                tmp_path.write_bytes(data)
                tmp_path.replace(path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
            digest = hashlib.sha256(data).hexdigest()
            self.store.db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, row["owner_id"], row["character_id"], row["source_content_id"], None,
                 "video" if kind == "video" else "video-manifest", mime_type, str(path), digest,
                 getattr(engine, "name", row["engine"]), "READY", now))
            self.store.db.execute(
                "UPDATE video_jobs SET status=?,output_artifact_id=?,updated_at=? WHERE video_job_id=?",
                ("SUCCEEDED", artifact_id, now, video_job_id))
            self.store.commit()
            self.store.event(row["owner_id"], "VIDEO_JOB_COMPLETED", "video_job", video_job_id,
                             {"artifact_id": artifact_id, "engine": row["engine"], "kind": kind})
            return self.get_job(video_job_id)
        except Exception as exc:
            self.store.db.execute("UPDATE video_jobs SET status=?,error=?,updated_at=? WHERE video_job_id=?",
                                  ("FAILED", str(exc), int(time.time()), video_job_id))
            self.store.commit()
            raise

    def create_job_from_latest_content(self, owner_id: str, character_id: str,
                                       brief: dict[str, Any] | None = None,
                                       engine: str = "test-manifest") -> dict[str, Any]:
        row = self.store.one(
            "SELECT content_id FROM content WHERE owner_id=? AND character_id=? "
            "AND status='READY' ORDER BY created_at DESC LIMIT 1",
            (owner_id, character_id),
        )
        if not row:
            raise ValueError("no_ready_image_content")
        return self.create_job_from_content(owner_id, row["content_id"], brief, engine)

    def create_job_from_content(self, owner_id: str, content_id: str,
                                brief: dict[str, Any] | None = None,
                                engine: str = "test-manifest") -> dict[str, Any]:
        row = self.store.one(
            "SELECT content_id,character_id FROM content WHERE content_id=? AND owner_id=?",
            (content_id, owner_id),
        )
        if not row:
            raise ValueError("content_not_found")
        assets = self.store.q(
            "SELECT artifact_id FROM artifacts WHERE owner_id=? AND content_id=? "
            "AND status='READY' ORDER BY created_at DESC",
            (owner_id, content_id),
        )
        source_asset_ids = [a["artifact_id"] for a in assets]
        if not source_asset_ids:
            raise ValueError("content_has_no_ready_artifacts")
        payload = dict(brief or {})
        payload.setdefault("source", "image-content")
        return self.create_job(
            owner_id,
            row["character_id"],
            source_content_id=content_id,
            source_asset_ids=source_asset_ids,
            brief=payload,
            engine=engine,
        )

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
        return {"engines": self.engines(), "contract_version": 2,
                "budget": self.budget_policy.describe()}
