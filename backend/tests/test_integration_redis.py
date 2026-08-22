"""Optional Redis integration tests."""
import uuid

import pytest
from tests.conftest_integration import REDIS_URL

pytestmark = [pytest.mark.asyncio, pytest.mark.redis]


async def test_redis_connection_and_set_get(redis_client):
    key = f"integration:{uuid.uuid4()}"
    await redis_client.set(key, "ok", ex=30)
    assert await redis_client.get(key) == "ok"
    await redis_client.delete(key)


async def test_redis_cache_pattern(redis_client):
    key = f"cache:recommendation:{uuid.uuid4()}"
    await redis_client.hset(key, mapping={"decision": "WAIT", "confidence": "50"})
    assert await redis_client.hgetall(key) == {"decision": "WAIT", "confidence": "50"}
    await redis_client.delete(key)


async def test_redis_failure_recovery(redis_client):
    await redis_client.ping()
    await redis_client.aclose()
    # A new client models recovery after a dropped connection.
    import redis.asyncio as redis
    replacement = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        assert await replacement.ping() is True
    finally:
        await replacement.aclose()


async def test_redis_cache_service_roundtrip():
    """End-to-end: the app-level RedisCache service reads back what it wrote."""
    from app.services.cache import RedisCache

    cache = RedisCache(url=REDIS_URL, prefix="fxai_test", default_ttl=30)
    key = f"decision:{uuid.uuid4()}"
    try:
        await cache.set_json(key, {"decision": "WAIT", "confidence": 50.0})
        assert await cache.get_json(key) == {"decision": "WAIT", "confidence": 50.0}
    finally:
        await cache.delete(key)
        await cache.close()


async def test_redis_cache_service_scopes_aidecision():
    """The AI decision engine caches by symbol and returns cached hits."""
    from app.services.cache import RedisCache
    from app.services.ai_decision import AIDecisionService, DecisionResult
    from unittest.mock import AsyncMock

    cache = RedisCache(url=REDIS_URL, prefix="fxai_test")
    svc = AIDecisionService(
        indicator_repo=AsyncMock(),
        smc_repo=AsyncMock(),
        candle_repo=AsyncMock(),
        cache=cache,
        cache_ttl=30,
    )
    svc._run_analysis = AsyncMock(
        return_value=DecisionResult(symbol="AUDUSD", decision="SELL", confidence=60.0)
    )
    key = "ai:decision:AUDUSD"
    try:
        await cache.delete(key)
        result1 = await svc.analyze("AUDUSD")
        assert result1.decision == "SELL"
        assert svc._run_analysis.await_count == 1
        result2 = await svc.analyze("AUDUSD")
        assert result2.decision == "SELL"
        assert svc._run_analysis.await_count == 1  # cache hit, no recompute
    finally:
        await cache.delete(key)
        await cache.close()

