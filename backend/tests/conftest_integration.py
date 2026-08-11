"""Optional PostgreSQL/Redis integration fixtures.

The integration suite never makes local services a prerequisite for the normal
SQLite test suite.  Set DATABASE_URL/REDIS_URL to point at test services.
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://forexai:forexai_secret@localhost:5432/forexai",
)
REDIS_URL = os.getenv("REDIS_URL")


def _service_reachable(url: str, default_port: int) -> bool:
    parsed = urlparse(url.replace("+asyncpg", ""))
    host = parsed.hostname or "localhost"
    port = parsed.port or default_port
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

POSTGRES_AVAILABLE = POSTGRES_URL.startswith("postgresql") and _service_reachable(POSTGRES_URL, 5432)
REDIS_AVAILABLE = bool(REDIS_URL) and _service_reachable(REDIS_URL, 6379)
if not POSTGRES_AVAILABLE:
    print("WARNING: PostgreSQL unavailable; integration DB fixtures fall back to SQLite.")
if REDIS_URL and not REDIS_AVAILABLE:
    print("WARNING: Redis unavailable; Redis integration tests will be skipped.")


def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: requires a reachable PostgreSQL service")
    config.addinivalue_line("markers", "redis: requires a reachable Redis service")


@pytest.fixture(scope="session")
def postgres_available():
    return POSTGRES_AVAILABLE


@pytest_asyncio.fixture(scope="session")
async def integration_engine():
    """Yield PostgreSQL, or SQLite as a useful local fallback when unavailable."""
    url = POSTGRES_URL if POSTGRES_AVAILABLE else "sqlite+aiosqlite:///./integration_test.db"
    engine = create_async_engine(url, echo=False, pool_size=2, max_overflow=0) if POSTGRES_AVAILABLE else create_async_engine(url, echo=False)
    from app.database import Base
    import app.models  # noqa: F401 - ensure every model is registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def integration_session(integration_engine) -> AsyncSession:
    factory = async_sessionmaker(integration_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def redis_client():
    if not REDIS_AVAILABLE:
        pytest.skip("Redis service is not available")
    import redis.asyncio as redis
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()
