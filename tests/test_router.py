"""Test router MUFAKAT (T5): quota RPM, circuit breaker, budget, fallback."""

import asyncio

import pytest

from mufakat.adapters.base import Adapter, AdapterError, Reply
from mufakat.router.budget import Budget, BudgetExceeded
from mufakat.router.fallback import CircuitBreaker, FallbackChain
from mufakat.router.quota import QuotaManager, TokenBucket


def test_token_bucket_rpm20_60_request():
    bucket = TokenBucket(capacity=20, refill_per_minute=20)
    assert sum(1 for _ in range(60) if bucket.allow()) == 20


def test_quota_manager_rpm20():
    qm = QuotaManager({"openrouter": {"rpm": 20, "rpd": 50}})
    assert sum(1 for _ in range(60) if qm.allow("openrouter")) == 20
    assert qm.allow("provider_tak_dikenal") is True  # tanpa batas = lolos


def test_circuit_breaker_buka_setelah_3_gagal():
    cb = CircuitBreaker(fail_threshold=3, open_seconds=600)
    for _ in range(3):
        cb.record_failure("deepseek")
    assert cb.is_open("deepseek")
    cb.record_success("deepseek")
    assert not cb.is_open("deepseek")


def test_budget_cost_dan_request():
    b = Budget(max_cost_usd=1.0, max_requests=2, max_wall_minutes=60)
    b.add_request()
    b.add_cost(0.5)
    b.check()
    b.add_request()
    with pytest.raises(BudgetExceeded):
        b.add_request()
    b2 = Budget(max_cost_usd=1.0, max_requests=100, max_wall_minutes=60)
    with pytest.raises(BudgetExceeded):
        b2.add_cost(1.5)  # add_cost langsung memeriksa batas


class _FailAdapter(Adapter):
    name = "gagal"
    family = "other"

    async def ask(self, prompt, system="", ctx=None):
        raise AdapterError("429 rate limit")

    def is_available(self):
        return True


class _OkAdapter(Adapter):
    name = "ok"
    family = "other"

    async def ask(self, prompt, system="", ctx=None):
        return Reply(text="jawaban cadangan", usage={}, provider="ok", family="other")

    def is_available(self):
        return True


def test_fallback_chain_jatuh_ke_cadangan():
    chain = FallbackChain(
        {"debater": ["gagal", "ok"]},
        {"gagal": _FailAdapter(), "ok": _OkAdapter()},
    )
    reply = asyncio.run(chain.ask_with_fallback("debater", "halo"))
    assert reply.text == "jawaban cadangan"


def test_fallback_chain_gagal_semua():
    chain = FallbackChain({"debater": ["gagal"]}, {"gagal": _FailAdapter()})
    with pytest.raises(AdapterError):
        asyncio.run(chain.ask_with_fallback("debater", "halo"))
