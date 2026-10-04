from __future__ import annotations

from pathlib import Path
from typing import Any

from .personal_ip import PersonalIPEngine, PersonalIP, PersonalIPSeed
from .personal_ip_store import PersonalIPStore


class PersistentPersonalIPEngine(PersonalIPEngine):
    """PersonalIPEngine backed by SQLite.

    The in-memory engine remains the business-rule layer; this adapter makes
    its durable state survive restarts and exposes a safe owner-scoped facade.
    """

    def __init__(self, database: str | Path):
        super().__init__()
        self.store = PersonalIPStore(database)
        self._hydrate()

    def close(self) -> None:
        self.store.close()

    def _hydrate(self) -> None:
        # Hydration intentionally reconstructs only persisted domain state.
        # New instances therefore start with the same IPs and boundaries.
        rows = self.store.db.execute(
            "SELECT * FROM personal_ip_seeds ORDER BY created_at ASC"
        ).fetchall()
        for row in rows:
            seed = PersonalIPSeed(
                seed_id=row["seed_id"],
                owner_id=row["owner_id"],
                consented=bool(row["consented"]),
                image_hash=row["image_hash"],
                created_at=row["created_at"],
                authenticity=row["authenticity"],
            )
            self.seeds[seed.seed_id] = seed

        rows = self.store.db.execute(
            "SELECT * FROM personal_ips ORDER BY created_at ASC"
        ).fetchall()
        for row in rows:
            ip = self.store._row_to_ip(row)
            self.ips[ip.personal_ip_id] = ip
            self.boundaries[ip.personal_ip_id] = self.store.get_boundaries(
                ip.personal_ip_id
            )
            self.history[ip.personal_ip_id] = self.store.get_history(
                ip.personal_ip_id
            )

    def create_seed(self, owner_id: str, image_bytes: bytes, **kwargs: Any) -> PersonalIPSeed:
        seed = super().create_seed(owner_id, image_bytes, **kwargs)
        self.store.save_seed(seed)
        return seed

    def create_personal_ip(
        self,
        owner_id: str,
        display_name: str,
        goal: str = "explore",
        *,
        seed_id: str | None = None,
    ) -> PersonalIP:
        ip = super().create_personal_ip(
            owner_id, display_name, goal, seed_id=seed_id
        )
        # Replace the transient snapshot with the durable canonical state.
        self.store.save_ip(ip, self.boundaries[ip.personal_ip_id])
        self.history[ip.personal_ip_id] = self.store.get_history(ip.personal_ip_id)
        return ip

    def set_boundaries(self, personal_ip_id: str, **changes: bool) -> dict[str, bool]:
        result = super().set_boundaries(personal_ip_id, **changes)
        ip = self._get(personal_ip_id)
        self.store.save_state(ip, result, "BOUNDARIES_CHANGED")
        self.history[personal_ip_id] = self.store.get_history(personal_ip_id)
        return result

    def freeze(self, personal_ip_id: str) -> PersonalIP:
        ip = super().freeze(personal_ip_id)
        self.store.save_state(ip, self.boundaries[personal_ip_id], "FROZEN")
        self.history[personal_ip_id] = self.store.get_history(personal_ip_id)
        return ip

    def unfreeze(self, personal_ip_id: str) -> PersonalIP:
        ip = super().unfreeze(personal_ip_id)
        self.store.save_state(ip, self.boundaries[personal_ip_id], "UNFROZEN")
        self.history[personal_ip_id] = self.store.get_history(personal_ip_id)
        return ip

    def apply_signals(self, personal_ip_id: str, **signals: Any) -> PersonalIP:
        ip = super().apply_signals(personal_ip_id, **signals)
        extra = {"verified": bool(signals.get("verified", False))}
        self.store.save_state(ip, self.boundaries[personal_ip_id], "SIGNALS_APPLIED", extra)
        self.history[personal_ip_id] = self.store.get_history(personal_ip_id)
        return ip

    def owner_ips(self, owner_id: str) -> list[PersonalIP]:
        return self.store.list_ips(owner_id)

    def owner_passports(self, owner_id: str) -> list[dict[str, Any]]:
        return [
            self.store.passport(ip.personal_ip_id)
            for ip in self.store.list_ips(owner_id)
        ]

    def public_passport(self, personal_ip_id: str) -> dict[str, Any]:
        ip = self._get(personal_ip_id)
        return self.store.passport(ip.personal_ip_id)

    def assert_owner(self, personal_ip_id: str, owner_id: str) -> PersonalIP:
        ip = self._get(personal_ip_id)
        if ip.owner_id != owner_id:
            raise PermissionError("owner_forbidden")
        return ip
