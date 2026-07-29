"""Test fixtures and configuration for forexai-terminal tests."""

import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create and drop all tables before and after each test using SQLite."""
    from app.database import Base

    test_engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db",
        echo=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async SQLite database session for tests."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db",
        echo=False,
    )
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_session() as session:
        yield session

    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP test client with the database session overridden."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_mt5_client():
    """Return a fresh MockMT5Client for testing."""
    from app.services.mt5_client import MockMT5Client, set_mt5_client

    mock = MockMT5Client()
    set_mt5_client(mock)
    return mock


@pytest.fixture
def auth_headers():
    """Return auth headers for a test user."""
    from app.utils.security import create_access_token

    user_id = str(uuid.uuid4())
    token = create_access_token(data={"sub": user_id})
    return {"Authorization": f"Bearer {token}"}
