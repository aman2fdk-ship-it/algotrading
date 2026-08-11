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
    await redis_client.close()
    # A new client models recovery after a dropped connection.
    import redis.asyncio as redis
    replacement = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        assert await replacement.ping() is True
    finally:
        await replacement.aclose()
