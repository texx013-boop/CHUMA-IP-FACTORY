from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .personal_ip import PersonalIP, PersonalIPSeed


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> int:
    return int(time.time())


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class PersonalIPStore:
    """Durable SQLite storage for CHUMA ME.

    The store keeps owner/IP/seed/boundary/history/event state locally and
    provider-neutrally. Binary image bytes are deliberately not stored here;
    only a content hash is persisted.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS personal_ip_schema (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS personal_ip_seeds (
                seed_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                consented INTEGER NOT NULL,
                image_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                authenticity TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS personal_ips (
                personal_ip_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                recognition REAL NOT NULL DEFAULT 0,
                audience REAL NOT NULL DEFAULT 0,
                reputation REAL NOT NULL DEFAULT 50,
                momentum REAL NOT NULL DEFAULT 0,
                ip_health REAL NOT NULL DEFAULT 100,
                ip_score REAL NOT NULL DEFAULT 0,
                frozen INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personal_ips_owner
                ON personal_ips(owner_id);

            CREATE TABLE IF NOT EXISTS personal_ip_boundaries (
                personal_ip_id TEXT NOT NULL,
                boundary TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                PRIMARY KEY(personal_ip_id, boundary),
                FOREIGN KEY(personal_ip_id) REFERENCES personal_ips(personal_ip_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS personal_ip_history (
                history_id TEXT PRIMARY KEY,
                personal_ip_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(personal_ip_id) REFERENCES personal_ips(personal_ip_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_personal_ip_history_ip
                ON personal_ip_history(personal_ip_id, created_at);

            CREATE TABLE IF NOT EXISTS personal_ip_events (
                event_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personal_ip_events_owner
                ON personal_ip_events(owner_id, created_at);
            """
        )
        self.db.execute(
            "INSERT OR REPLACE INTO personal_ip_schema(key,value) VALUES('version','1')"
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def save_seed(self, seed: PersonalIPSeed) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO personal_ip_seeds
               (seed_id,owner_id,consented,image_hash,created_at,authenticity)
               VALUES(?,?,?,?,?,?)""",
            (
                seed.seed_id,
                seed.owner_id,
                int(seed.consented),
                seed.image_hash,
                seed.created_at,
                seed.authenticity,
            ),
        )
        self.event(
            seed.owner_id,
            "PERSONAL_IP_SEED_CREATED",
            seed.seed_id,
            {"authenticity": seed.authenticity},
            commit=False,
        )
        self.db.commit()

    def get_seed(self, seed_id: str) -> PersonalIPSeed | None:
        row = self.db.execute(
            "SELECT * FROM personal_ip_seeds WHERE seed_id=?", (seed_id,)
        ).fetchone()
        if not row:
            return None
        return PersonalIPSeed(
            seed_id=row["seed_id"],
            owner_id=row["owner_id"],
            consented=bool(row["consented"]),
            image_hash=row["image_hash"],
            created_at=row["created_at"],
            authenticity=row["authenticity"],
        )

    def save_ip(self, ip: PersonalIP, boundaries: dict[str, bool]) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO personal_ips
               (personal_ip_id,owner_id,display_name,goal,status,recognition,
                audience,reputation,momentum,ip_health,ip_score,frozen,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ip.personal_ip_id,
                ip.owner_id,
                ip.display_name,
                ip.goal,
                ip.status,
                ip.recognition,
                ip.audience,
                ip.reputation,
                ip.momentum,
                ip.ip_health,
                ip.ip_score,
                int(ip.frozen),
                _now(),
            ),
        )
        for key, value in boundaries.items():
            self.db.execute(
                """INSERT OR REPLACE INTO personal_ip_boundaries
                   (personal_ip_id,boundary,enabled) VALUES(?,?,?)""",
                (ip.personal_ip_id, key, int(value)),
            )
        self.snapshot(ip, "CREATED", commit=False)
        self.db.commit()

    def get_ip(self, personal_ip_id: str) -> PersonalIP | None:
        row = self.db.execute(
            "SELECT * FROM personal_ips WHERE personal_ip_id=?",
            (personal_ip_id,),
        ).fetchone()
        if not row:
            return None
        return PersonalIP(
            personal_ip_id=row["personal_ip_id"],
            owner_id=row["owner_id"],
            display_name=row["display_name"],
            goal=row["goal"],
            status=row["status"],
            recognition=row["recognition"],
            audience=row["audience"],
            reputation=row["reputation"],
            momentum=row["momentum"],
            ip_health=row["ip_health"],
            ip_score=row["ip_score"],
            frozen=bool(row["frozen"]),
        )

    def list_ips(self, owner_id: str) -> list[PersonalIP]:
        rows = self.db.execute(
            "SELECT * FROM personal_ips WHERE owner_id=? ORDER BY created_at ASC",
            (owner_id,),
        ).fetchall()
        return [self._row_to_ip(row) for row in rows]

    @staticmethod
    def _row_to_ip(row: sqlite3.Row) -> PersonalIP:
        return PersonalIP(
            personal_ip_id=row["personal_ip_id"],
            owner_id=row["owner_id"],
            display_name=row["display_name"],
            goal=row["goal"],
            status=row["status"],
            recognition=row["recognition"],
            audience=row["audience"],
            reputation=row["reputation"],
            momentum=row["momentum"],
            ip_health=row["ip_health"],
            ip_score=row["ip_score"],
            frozen=bool(row["frozen"]),
        )

    def save_state(
        self,
        ip: PersonalIP,
        boundaries: dict[str, bool],
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.db.execute(
            """UPDATE personal_ips SET status=?,recognition=?,audience=?,
               reputation=?,momentum=?,ip_health=?,ip_score=?,frozen=?
               WHERE personal_ip_id=?""",
            (
                ip.status,
                ip.recognition,
                ip.audience,
                ip.reputation,
                ip.momentum,
                ip.ip_health,
                ip.ip_score,
                int(ip.frozen),
                ip.personal_ip_id,
            ),
        )
        for key, value in boundaries.items():
            self.db.execute(
                """INSERT OR REPLACE INTO personal_ip_boundaries
                   (personal_ip_id,boundary,enabled) VALUES(?,?,?)""",
                (ip.personal_ip_id, key, int(value)),
            )
        self.snapshot(ip, reason, extra, commit=False)
        self.db.commit()

    def get_boundaries(self, personal_ip_id: str) -> dict[str, bool]:
        rows = self.db.execute(
            """SELECT boundary,enabled FROM personal_ip_boundaries
               WHERE personal_ip_id=?""",
            (personal_ip_id,),
        ).fetchall()
        return {row["boundary"]: bool(row["enabled"]) for row in rows}

    def get_history(self, personal_ip_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """SELECT snapshot_json FROM personal_ip_history
               WHERE personal_ip_id=? ORDER BY created_at ASC, history_id ASC""",
            (personal_ip_id,),
        ).fetchall()
        return [json.loads(row["snapshot_json"]) for row in rows]

    def event(
        self,
        owner_id: str,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        *,
        commit: bool = True,
    ) -> None:
        self.db.execute(
            """INSERT INTO personal_ip_events
               (event_id,owner_id,event_type,aggregate_id,payload_json,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                _uid("EV"),
                owner_id,
                event_type,
                aggregate_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                _now(),
            ),
        )
        if commit:
            self.db.commit()

    def snapshot(
        self,
        ip: PersonalIP,
        reason: str,
        extra: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> dict[str, Any]:
        snap = asdict(ip)
        snap["reason"] = reason
        if extra:
            snap.update(extra)
        self.db.execute(
            """INSERT INTO personal_ip_history
               (history_id,personal_ip_id,reason,snapshot_json,created_at)
               VALUES(?,?,?,?,?)""",
            (
                _uid("HIST"),
                ip.personal_ip_id,
                reason,
                json.dumps(snap, ensure_ascii=False, sort_keys=True, default=str),
                _now(),
            ),
        )
        self.event(
            ip.owner_id,
            "PERSONAL_IP_SNAPSHOT",
            ip.personal_ip_id,
            snap,
            commit=False,
        )
        if commit:
            self.db.commit()
        return snap

    def provenance_hash(self, personal_ip_id: str) -> str:
        return _hash(self.get_history(personal_ip_id))

    def passport(self, personal_ip_id: str) -> dict[str, Any]:
        ip = self.get_ip(personal_ip_id)
        if not ip:
            raise KeyError("personal_ip_not_found")
        return {
            "schema_version": 1,
            "personal_ip_id": ip.personal_ip_id,
            "owner_id": ip.owner_id,
            "display_name": ip.display_name,
            "goal": ip.goal,
            "status": ip.status,
            "frozen": ip.frozen,
            "metrics": {
                "personal_ip_score": ip.ip_score,
                "recognition": ip.recognition,
                "audience": ip.audience,
                "reputation": ip.reputation,
                "momentum": ip.momentum,
                "ip_health": ip.ip_health,
            },
            "commercial_value": "NOT_A_FINANCIAL_VALUATION",
            "boundaries": self.get_boundaries(personal_ip_id),
            "history_count": len(self.get_history(personal_ip_id)),
            "provenance_hash": self.provenance_hash(personal_ip_id),
        }
