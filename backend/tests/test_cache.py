"""Tests for the Redis cache service and its AI service integration.

Covers:
* RedisCache graceful degradation (disabled / Redis down => no-op, no crash)
* RedisCache JSON round-trip and key namespacing (via an injected fake client)
* AIDecisionService cache hit/miss and Redis-down fallback through a fake cache
"""
import pytest
from unittest.mock import AsyncMock

from app.services.cache import RedisCache
from app.services.ai_decision import AIDecisionService, DecisionResult

pytestmark = pytest.mark.asyncio


# ── Helpers ────────────────────────────────────────────────────────────────────

class FakeRedisClient:
    """Stand-in for a redis.asyncio client with just get/set/delete."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)

    async def aclose(self):
        pass


class FakeCache:
    """In-memory cache with an optional 'down' mode to model a Redis outage."""

    def __init__(self, fail: bool = False):
        self.store: dict[str, object] = {}
        self.fail = fail

    async def get_json(self, key: str):
        if self.fail:
            raise ConnectionError("Redis is down")
        return self.store.get(key)

    async def set_json(self, key: str, value, ttl=None):
        if self.fail:
            raise ConnectionError("Redis is down")
        self.store[key] = value


def _build_service(cache=None, ttl=None) -> AIDecisionService:
    svc = AIDecisionService(
        indicator_repo=AsyncMock(),
        smc_repo=AsyncMock(),
        candle_repo=AsyncMock(),
        recommendation_repo=None,
        cache=cache,
        cache_ttl=ttl,
    )
    svc._run_analysis = AsyncMock(  # isolate the compute step for cache tests
        return_value=DecisionResult(
            symbol="EURUSD",
            decision="BUY",
            confidence=75.0,
            entry_price=1.0850,
            stop_loss=1.0800,
            trend="Bullish",
            market_bias="Buy",
            risk_level="Low",
            reasoning="test",
            timeframe_scores={"H1": 0.5},
        )
    )
    return svc


# ── RedisCache: graceful degradation ───────────────────────────────────────────

async def test_disabled_cache_is_a_noop_miss():
    cache = RedisCache(enabled=False)
    assert await cache.get("k") is None
    assert await cache.get_json("k") is None
    await cache.set("k", "v")  # must not raise
    await cache.set_json("k", {"a": 1})  # must not raise


async def test_no_url_cache_is_a_noop_miss():
    cache = RedisCache(url=None, enabled=True)
    assert await cache.get("k") is None
    await cache.set("k", "v")  # must not raise


async def test_graceful_when_redis_unreachable():
    # Connection to a closed port on loopback fails fast.
    cache = RedisCache(url="redis://127.0.0.1:6399/0", enabled=True)
    assert await cache.get("unreachable-key") is None
    await cache.set("unreachable-key", "v")  # must not raise
    assert await cache.get_json("unreachable-key") is None
    await cache.close()  # must not raise


async def test_recovers_client_handle_after_failure():
    cache = RedisCache(url="redis://127.0.0.1:6399/0", enabled=True)
    await cache.get("a")  # fails, closes the client
    assert cache._client is None
    await cache.get("b")  # builds a fresh client and retries without raising
    assert await cache.get("b") is None


# ── RedisCache: JSON round-trip & namespacing (fake client) ───────────────────

async def test_json_roundtrip_and_key_prefix(monkeypatch):
    cache = RedisCache(url="redis://ignored:6379/0", prefix="fxai")
    fake = FakeRedisClient()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)

    await cache.set_json("decision", {"decision": "BUY", "confidence": 80.0})
    assert fake.store["fxai:decision"] == '{"decision": "BUY", "confidence": 80.0}'
    assert await cache.get_json("decision") == {"decision": "BUY", "confidence": 80.0}

    await cache.set("raw", "123", ttl=10)
    assert fake.store["fxai:raw"] == "123"
    assert await cache.get("raw") == "123"

    await cache.delete("decision")
    assert "fxai:decision" not in fake.store


# ── AIDecisionService caching ──────────────────────────────────────────────────

async def test_analyze_serves_cache_hit_without_recompute():
    cache = FakeCache()
    svc = _build_service(cache=cache, ttl=30)

    first = await svc.analyze("EURUSD")
    assert svc._run_analysis.await_count == 1
    assert first.decision == "BUY"

    second = await svc.analyze("EURUSD")
    assert svc._run_analysis.await_count == 1  # not recomputed on cache hit
    assert second.decision == first.decision
    # The result was stored at the service-level cache key.
    assert await cache.get_json("ai:decision:EURUSD") is not None


async def test_analyze_recomputes_when_redis_down():
    cache = FakeCache(fail=True)  # models a Redis outage
    svc = _build_service(cache=cache, ttl=30)

    result = await svc.analyze("GBPUSD")
    assert result.decision == "BUY"  # graceful — still produces a result
    assert svc._run_analysis.await_count == 1
    # A second call also falls back to compute (cache write keeps failing).
    await svc.analyze("GBPUSD")
    assert svc._run_analysis.await_count == 2


async def test_analyze_computes_every_time_when_no_cache():
    svc = _build_service(cache=None)
    await svc.analyze("USDJPY")
    await svc.analyze("USDJPY")
    assert svc._run_analysis.await_count == 2
