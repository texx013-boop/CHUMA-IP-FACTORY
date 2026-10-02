import pytest

from chuma_ip_factory.budget import BudgetGuardProvider, BudgetPolicy, PaidGenerationBlocked


class FakeProvider:
    name = "fake-metered"
    connected = True

    def generate(self, request):
        return {"ok": True}


def test_default_policy_is_zero_budget(monkeypatch):
    for key in (
        "CHUMA_SPEND_MODE",
        "CHUMA_ALLOW_PAID_GENERATION",
        "CHUMA_MONTHLY_SOFT_CAP_USD",
        "CHUMA_MONTHLY_HARD_CAP_USD",
    ):
        monkeypatch.delenv(key, raising=False)
    policy = BudgetPolicy.from_env()
    assert policy.mode == "free"
    assert policy.allow_paid is False
    assert policy.monthly_soft_cap_usd == 0
    assert policy.monthly_hard_cap_usd == 0
    assert policy.allows("free")
    assert not policy.allows("metered")


def test_paid_provider_is_blocked_by_default(monkeypatch):
    monkeypatch.setenv("CHUMA_SPEND_MODE", "free")
    monkeypatch.setenv("CHUMA_ALLOW_PAID_GENERATION", "true")
    policy = BudgetPolicy.from_env()
    provider = BudgetGuardProvider(FakeProvider(), policy)
    assert provider.connected is False
    with pytest.raises(PaidGenerationBlocked):
        provider.generate({})


def test_micro_budget_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv("CHUMA_SPEND_MODE", "micro")
    monkeypatch.setenv("CHUMA_ALLOW_PAID_GENERATION", "true")
    monkeypatch.setenv("CHUMA_MONTHLY_SOFT_CAP_USD", "5")
    monkeypatch.setenv("CHUMA_MONTHLY_HARD_CAP_USD", "10")
    policy = BudgetPolicy.from_env()
    provider = BudgetGuardProvider(FakeProvider(), policy)
    assert provider.connected is True
    assert provider.generate({}) == {"ok": True}


def test_free_provider_can_run_in_free_mode(monkeypatch):
    monkeypatch.setenv("CHUMA_SPEND_MODE", "free")
    policy = BudgetPolicy.from_env()
    provider = BudgetGuardProvider(FakeProvider(), policy, cost_class="free")
    assert provider.connected is True
    assert provider.generate({}) == {"ok": True}
