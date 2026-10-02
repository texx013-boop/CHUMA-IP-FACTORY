from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

MODES = ("free", "micro", "production")


class PaidGenerationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetPolicy:
    mode: str = "free"
    allow_paid: bool = False
    monthly_soft_cap_usd: float = 0.0
    monthly_hard_cap_usd: float = 0.0

    @classmethod
    def from_env(cls) -> "BudgetPolicy":
        mode = os.getenv("CHUMA_SPEND_MODE", "free").strip().lower() or "free"
        if mode not in MODES:
            raise ValueError(f"invalid CHUMA_SPEND_MODE: {mode}")
        allow_paid = os.getenv("CHUMA_ALLOW_PAID_GENERATION", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        soft = float(os.getenv("CHUMA_MONTHLY_SOFT_CAP_USD", "0"))
        hard = float(os.getenv("CHUMA_MONTHLY_HARD_CAP_USD", "0"))
        if soft < 0 or hard < 0 or (hard and soft > hard):
            raise ValueError("invalid CHUMA monthly budget caps")
        if mode == "free":
            allow_paid = False
        return cls(mode, allow_paid, soft, hard)

    def allows(self, cost_class: str) -> bool:
        if (cost_class or "free").strip().lower() in {"free", "free-credit", "zero-cost"}:
            return True
        return self.allow_paid and self.mode in {"micro", "production"}

    def describe(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allow_paid": self.allow_paid,
            "monthly_soft_cap_usd": self.monthly_soft_cap_usd,
            "monthly_hard_cap_usd": self.monthly_hard_cap_usd,
            "subscriptions": False,
            "auto_upgrade": False,
        }


class BudgetGuardProvider:
    """Blocks metered providers unless the explicit budget policy allows them."""

    def __init__(self, provider: Any, policy: BudgetPolicy, cost_class: str = "metered"):
        self.provider = provider
        self.policy = policy
        self.cost_class = cost_class
        self.name = getattr(provider, "name", "unknown")
        self.connected = bool(getattr(provider, "connected", False)) and policy.allows(cost_class)
        for attr in ("max_attempts", "timeout", "retry_delay"):
            if hasattr(provider, attr):
                setattr(self, attr, getattr(provider, attr))

    def generate(self, request: dict) -> dict:
        if not self.policy.allows(self.cost_class):
            raise PaidGenerationBlocked("paid_generation_blocked_by_budget_policy")
        return self.provider.generate(request)
