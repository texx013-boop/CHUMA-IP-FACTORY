from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class VideoCombain:
    """Provider-neutral video production boundary for SHUMA.SPACE.

    The factory owns identity, assets and provenance. This module owns the
    video-job contract so a real video engine can be connected later without
    changing the user-facing product.
    """

    def __init__(self, factory):
        self.factory = factory
        self.store = factory.store
        self.root = Path(factory.asset_root) / "video"
        self.root.mkdir(parents=True, exist_ok=True)
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
                "connected": False,
                "mode": "api",
                "description": "Точка подключения внешнего видеогенератора",
            },
        ]

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
                job_id,
                owner_id,
                character_id,
                source_content_id,
                json.dumps(source_asset_ids or [], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                engine,
                "QUEUED",
                None,
                None,
                now,
                now,
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
            manifest = {
                "type": "shuma_video_job",
                "version": 1,
                "video_job_id": video_job_id,
                "owner_id": row["owner_id"],
                "character_id": row["character_id"],
                "source_content_id": row["source_content_id"],
                "source_asset_ids": json.loads(row["source_asset_ids_json"]),
                "brief": brief,
                "engine": row["engine"],
                "created_at": now,
                "status": "READY_FOR_RENDER",
            }
            data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            path = self.root / f"{video_job_id}.json"
            path.write_bytes(data)
            artifact_id = _uid("VA")
            self.store.db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    row["owner_id"],
                    row["character_id"],
                    row["source_content_id"],
                    None,
                    "video-manifest",
                    "application/json",
                    str(path),
                    __import__("hashlib").sha256(data).hexdigest(),
                    "video-combain",
                    "READY",
                    now,
                ),
            )
            self.store.db.execute(
                "UPDATE video_jobs SET status=?,output_artifact_id=?,updated_at=? WHERE video_job_id=?",
                ("SUCCEEDED", artifact_id, now, video_job_id),
            )
            self.store.commit()
            self.store.event(
                row["owner_id"],
                "VIDEO_JOB_COMPLETED",
                "video_job",
                video_job_id,
                {"artifact_id": artifact_id, "engine": row["engine"]},
            )
            return self.get_job(video_job_id)
        except Exception as exc:
            self.store.db.execute(
                "UPDATE video_jobs SET status=?,error=?,updated_at=? WHERE video_job_id=?",
                ("FAILED", str(exc), int(time.time()), video_job_id),
            )
            self.store.commit()
            raise

    def get_job(self, video_job_id: str):
        row = self.store.one(
            "SELECT * FROM video_jobs WHERE video_job_id=?", (video_job_id,)
        )
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
        return {"engines": self.engines(), "contract_version": 1}
