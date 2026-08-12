"""Optional PostgreSQL/Redis integration fixtures.

The integration suite never makes local services a prerequisite for the normal
SQLite test suite.  Set DATABASE_URL/REDIS_URL to point at dedicated TEST
services (e.g. a local ``forexai_test`` PostgreSQL database and a Redis
instance) to run the 9 integration tests; when the services are not usable the
tests skip gracefully.

Safety: create_all/drop_all only ever run against a database whose name
contains "test".  If DATABASE_URL points at any other database (e.g. the
staging or a docker-compose dev database), the integration DB tests skip and a
WARNING is printed — the schema of a non-test database is never modified.
"""
from __future__ import annotations

import asyncio
import os
import socket
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# The default is only a placeholder for environments with no DATABASE_URL set;
# it points at a local database that normally does not exist, so the suite
# skips the integration tests unless an explicit DATABASE_URL is provided.
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


def _database_name(url: str) -> str:
    parsed = urlparse(url.replace("+asyncpg", ""))
    return (parsed.path or "").lstrip("/")


def _postgres_available(url: str) -> bool:
    """True only when the database named in ``url`` actually accepts a login.

    A plain TCP check is not enough: PostgreSQL may listen on 5432 while the
    role/database in the URL does not exist, which previously turned the
    integration tests into confusing connection errors instead of skips.
    """
    if not url.startswith("postgresql"):
        return False
    parsed = urlparse(url.replace("+asyncpg", ""))

    async def _probe() -> None:
        import asyncpg

        conn = await asyncpg.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=_database_name(url),
            timeout=2,
            command_timeout=2,
        )
        await conn.close()

    try:
        asyncio.run(_probe())
        return True
    except Exception:
        return False


def _redis_available(url: str | None) -> bool:
    """True only when ``url`` is set and accepts an authenticated PING."""
    if not url or not _service_reachable(url, 6379):
        return False
    parsed = urlparse(url)

    async def _probe() -> None:
        import redis.asyncio as aioredis

        client = aioredis.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            db=int((parsed.path or "/0").lstrip("/") or 0),
            socket_timeout=2,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    try:
        asyncio.run(_probe())
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_available(POSTGRES_URL)
if POSTGRES_AVAILABLE and "test" not in _database_name(POSTGRES_URL):
    # Hard safety guard: never create/drop schema on a non-test database.
    print(
        f"WARNING: DATABASE_URL points at non-test database {_database_name(POSTGRES_URL)!r}; "
        "integration DB tests will SKIP to protect it. Point DATABASE_URL at a "
        "dedicated test database (e.g. postgresql+asyncpg://...@127.0.0.1:5432/forexai_test) "
        "to run them."
    )
    POSTGRES_AVAILABLE = False
elif not POSTGRES_AVAILABLE and POSTGRES_URL.startswith("postgresql"):
    print("WARNING: PostgreSQL unavailable; integration DB fixtures fall back to SQLite.")
REDIS_AVAILABLE = _redis_available(REDIS_URL)
if REDIS_URL and not REDIS_AVAILABLE:
    print("WARNING: Redis unavailable; Redis integration tests will be skipped.")


def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: requires a reachable PostgreSQL service")
    config.addinivalue_line("markers", "redis: requires a reachable Redis service")


@pytest.fixture(scope="session")
def postgres_available():
    return POSTGRES_AVAILABLE


@pytest_asyncio.fixture
async def integration_engine():
    """Yield PostgreSQL, or SQLite as a useful local fallback when unavailable.

    Function-scoped: the engine is created, used and disposed entirely within
    one test's event loop (see ``pytest.ini``), so its connections are never
    reused across loops.  NullPool keeps the connection count at zero between
    tests, so a failed test can never exhaust a fixed-size pool and cascade
    timeouts into later tests.
    """
    url = POSTGRES_URL if POSTGRES_AVAILABLE else "sqlite+aiosqlite:///./integration_test.db"
    engine = (
        create_async_engine(url, echo=False, poolclass=NullPool)
        if POSTGRES_AVAILABLE
        else create_async_engine(url, echo=False)
    )
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
