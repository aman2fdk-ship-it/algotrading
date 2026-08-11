"""Database integration checks; PostgreSQL tests are skipped when unavailable."""
import asyncio
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models.ai_recommendation import AIRecommendation
from app.models.user import User
from tests.conftest_integration import POSTGRES_AVAILABLE

pytestmark = [pytest.mark.asyncio, pytest.mark.postgres, pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL service is not available")]


async def test_crud_against_real_tables(integration_session):
    user = User(id=str(uuid.uuid4()), email=f"db-{uuid.uuid4()}@example.com", name="Integration", hashed_password="hash")
    integration_session.add(user)
    await integration_session.commit()
    found = await integration_session.scalar(select(User).where(User.id == user.id))
    assert found is not None and found.email == user.email
    await integration_session.delete(found)
    await integration_session.commit()
    assert await integration_session.scalar(select(User).where(User.id == user.id)) is None


async def test_json_column_support(integration_session):
    rec = AIRecommendation(symbol="EURUSD", decision="BUY", confidence=87.5, trend="Bullish", market_bias="Bullish", risk_level="Low", reasoning='{"signals":["EMA","RSI"]}', timeframe_scores='{"H1":0.9}')
    integration_session.add(rec)
    await integration_session.commit()
    loaded = await integration_session.scalar(select(AIRecommendation).where(AIRecommendation.id == rec.id))
    assert loaded is not None
    assert loaded.timeframe_scores == '{"H1":0.9}'


async def test_concurrent_writes(integration_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(integration_engine, class_=AsyncSession, expire_on_commit=False)
    users = [User(id=str(uuid.uuid4()), email=f"concurrent-{uuid.uuid4()}@example.com", name="Concurrent", hashed_password="hash") for _ in range(2)]
    async def insert(user):
        async with factory() as session:
            session.add(user)
            await session.commit()
    await asyncio.gather(*(insert(user) for user in users))
    async with factory() as session:
        assert len((await session.scalars(select(User).where(User.id.in_([u.id for u in users])))).all()) == 2


async def test_transaction_rollback(integration_session):
    user = User(id=str(uuid.uuid4()), email="rollback@example.com", name="Rollback", hashed_password="hash")
    integration_session.add(user)
    await integration_session.flush()
    await integration_session.rollback()
    assert await integration_session.scalar(select(User).where(User.id == user.id)) is None


async def test_connection_pool_recovery(integration_engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    factory = async_sessionmaker(integration_engine, class_=AsyncSession)
    async with factory() as session:
        await session.execute(select(User).limit(1))
    async with factory() as session:
        assert (await session.execute(text("SELECT 1"))).scalar() == 1


async def test_schema_matches_models(integration_engine):
    async with integration_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    expected = set(Base.metadata.tables)
    assert expected.issubset(tables)
    assert {c.name for c in Base.metadata.tables["users"].columns} == {"id", "email", "hashed_password", "name", "is_active", "is_verified", "avatar_url", "default_symbols", "timezone", "created_at", "updated_at", "last_login"}
