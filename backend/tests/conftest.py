"""Test fixtures and configuration for forexai-terminal tests."""

# Load optional service fixtures without changing the existing SQLite fixtures.
pytest_plugins = ("tests.conftest_integration",)

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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


@pytest_asyncio.fixture
async def auth_headers(db_session: AsyncSession):
    """Return auth headers for a test user. Also creates the user in the DB."""
    from app.utils.security import create_access_token
    from app.models.user import User
    from sqlalchemy import select

    user_id = str(uuid.uuid4())
    token = create_access_token(data={"sub": user_id})

    # Ensure the user exists in the DB
    result = await db_session.execute(select(User).where(User.id == user_id))
    existing = result.scalar_one_or_none()
    if existing is None:
        user = User(
            id=user_id,
            email=f"test-{user_id[:8]}@example.com",
            name="Test User",
            hashed_password="test_password_hash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

    return {"Authorization": f"Bearer {token}"}
