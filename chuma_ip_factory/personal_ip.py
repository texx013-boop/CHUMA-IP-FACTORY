from __future__ import annotations
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

PERSONAL_IP_SCHEMA_VERSION = 1

def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

def _now() -> int:
    return int(time.time())

def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()

@dataclass
class PersonalIPSeed:
    seed_id: str
    owner_id: str
    consented: bool
    image_hash: str
    created_at: int
    authenticity: str = "REAL"

@dataclass
class PersonalIP:
    personal_ip_id: str
    owner_id: str
    display_name: str
    goal: str
    status: str
    recognition: float = 0.0
    audience: float = 0.0
    reputation: float = 50.0
    momentum: float = 0.0
    ip_health: float = 100.0
    ip_score: float = 0.0
    frozen: bool = False

    def score(self) -> float:
        # Product metric, not a monetary valuation or promise of income.
        raw = (
            self.recognition * 0.28
            + self.audience * 0.18
            + self.reputation * 0.22
            + self.momentum * 0.17
            + self.ip_health * 0.15
        )
        self.ip_score = round(max(0.0, min(1000.0, raw * 10.0)), 2)
        return self.ip_score

class PersonalIPEngine:
    """Minimal, provider-neutral foundation for CHUMA ME.

    The engine stores consent/boundaries and turns verified product signals
    into a transparent Personal IP Score. It never treats the score as money.
    """

    GOALS = {"recognition", "audience", "business", "creative_career", "explore"}
    MODES = {"OBSERVE", "ASSIST", "AUTO", "PRO"}
    AUTHENTICITY = {"REAL", "AI_ASSISTED", "SYNTHETIC", "FICTION"}

    def __init__(self):
        self.seeds: dict[str, PersonalIPSeed] = {}
        self.ips: dict[str, PersonalIP] = {}
        self.events: list[dict[str, Any]] = {}
        self.events = []
        self.boundaries: dict[str, dict[str, bool]] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}

    def create_seed(
        self,
        owner_id: str,
        image_bytes: bytes,
        *,
        consented: bool,
        authenticity: str = "REAL",
    ) -> PersonalIPSeed:
        if not owner_id:
            raise ValueError("owner_id_required")
        if not image_bytes:
            raise ValueError("image_required")
        if not consented:
            raise PermissionError("explicit_consent_required")
        if authenticity not in self.AUTHENTICITY:
            raise ValueError("invalid_authenticity")
        seed = PersonalIPSeed(
            seed_id=_uid("PSEED"),
            owner_id=owner_id,
            consented=True,
            image_hash=hashlib.sha256(image_bytes).hexdigest(),
            created_at=_now(),
            authenticity=authenticity,
        )
        self.seeds[seed.seed_id] = seed
        self._event(owner_id, "PERSONAL_IP_SEED_CREATED", seed.seed_id, {"authenticity": authenticity})
        return seed

    def create_personal_ip(
        self,
        owner_id: str,
        display_name: str,
        goal: str = "explore",
        *,
        seed_id: str | None = None,
    ) -> PersonalIP:
        if goal not in self.GOALS:
            raise ValueError("invalid_goal")
        if seed_id:
            seed = self.seeds.get(seed_id)
            if not seed or seed.owner_id != owner_id or not seed.consented:
                raise PermissionError("invalid_personal_ip_seed")
        ip = PersonalIP(
            personal_ip_id=_uid("PIP"),
            owner_id=owner_id,
            display_name=display_name.strip() or "My IP",
            goal=goal,
            status="SEED",
        )
        self.ips[ip.personal_ip_id] = ip
        self.boundaries[ip.personal_ip_id] = {
            "face": True, "voice": False, "name": True,
            "character": True, "commercial_use": False,
        }
        self.history[ip.personal_ip_id] = []
        self._snapshot(ip, "CREATED")
        return ip

    def set_boundaries(self, personal_ip_id: str, **changes: bool) -> dict[str, bool]:
        ip = self._get(personal_ip_id)
        allowed = self.boundaries[personal_ip_id]
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError(f"unknown_boundary:{key}")
            if not isinstance(value, bool):
                raise TypeError(f"boundary_must_be_bool:{key}")
            allowed[key] = value
        self._event(ip.owner_id, "BOUNDARIES_CHANGED", personal_ip_id, allowed.copy())
        return allowed.copy()

    def freeze(self, personal_ip_id: str) -> PersonalIP:
        ip = self._get(personal_ip_id)
        ip.frozen = True
        ip.status = "FROZEN"
        self._snapshot(ip, "FROZEN")
        return ip

    def unfreeze(self, personal_ip_id: str) -> PersonalIP:
        ip = self._get(personal_ip_id)
        ip.frozen = False
        ip.status = "ACTIVE"
        self._snapshot(ip, "UNFROZEN")
        return ip

    def apply_signals(
        self,
        personal_ip_id: str,
        *,
        recognition: float = 0,
        audience: float = 0,
        reputation: float = 0,
        momentum: float = 0,
        ip_health: float = 0,
        verified: bool = False,
    ) -> PersonalIP:
        ip = self._get(personal_ip_id)
        if ip.frozen:
            raise PermissionError("personal_ip_frozen")
        # Verified achievements can improve recognition/reputation, but the
        # engine never invents or verifies a real-world event on its own.
        factor = 1.15 if verified else 1.0
        ip.recognition = self._bounded(ip.recognition + recognition * factor)
        ip.audience = self._bounded(ip.audience + audience)
        ip.reputation = self._bounded(ip.reputation + reputation * factor)
        ip.momentum = self._bounded(ip.momentum + momentum)
        ip.ip_health = self._bounded(ip.ip_health + ip_health)
        ip.status = "ACTIVE"
        ip.score()
        self._snapshot(ip, "SIGNALS_APPLIED", {"verified": verified})
        return ip

    def public_passport(self, personal_ip_id: str) -> dict[str, Any]:
        ip = self._get(personal_ip_id)
        return {
            "schema_version": PERSONAL_IP_SCHEMA_VERSION,
            "personal_ip_id": ip.personal_ip_id,
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
            "boundaries": self.boundaries[personal_ip_id].copy(),
            "provenance_hash": _hash(self.history[personal_ip_id]),
        }

    def _get(self, personal_ip_id: str) -> PersonalIP:
        ip = self.ips.get(personal_ip_id)
        if not ip:
            raise KeyError("personal_ip_not_found")
        return ip

    @staticmethod
    def _bounded(value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)

    def _event(self, owner_id: str, event_type: str, aggregate_id: str, payload: dict[str, Any]):
        self.events.append({
            "event_id": _uid("EV"),
            "owner_id": owner_id,
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "created_at": _now(),
        })

    def _snapshot(self, ip: PersonalIP, reason: str, extra: dict[str, Any] | None = None):
        snap = asdict(ip)
        snap["reason"] = reason
        if extra:
            snap.update(extra)
        self.history[ip.personal_ip_id].append(snap)
        self._event(ip.owner_id, "PERSONAL_IP_SNAPSHOT", ip.personal_ip_id, snap)
