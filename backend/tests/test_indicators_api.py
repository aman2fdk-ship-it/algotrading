"""Integration tests for Technical Indicator API endpoints."""

import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient

from app.models.user import User
from app.models.technical_indicator import TechnicalIndicator
from app.repositories.indicator_repository import IndicatorRepository


async def _create_test_user(db_session) -> User:
    """Create a test user and return it."""
    from app.utils.security import hash_password

    user = User(
        id=str(uuid.uuid4()),
        email="test@example.com",
        hashed_password=hash_password("password123"),
        name="Test User",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_headers_for(user: User) -> dict:
    """Generate auth headers for a user."""
    from app.utils.security import create_access_token
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def make_indicator(
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    ts_offset: int = 0,
) -> TechnicalIndicator:
    """Create a test TechnicalIndicator with sample values."""
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return TechnicalIndicator(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(base.timestamp() + ts_offset * 3600, tz=timezone.utc),
        ema_20=1.0850,
        ema_50=1.0840,
        ema_200=1.0800,
        supertrend_direction=1,
        supertrend_value=1.0820,
        adx=25.5,
        rsi=55.0,
        macd_line=0.0005,
        macd_signal=0.0003,
        macd_histogram=0.0002,
        stoch_k=65.0,
        stoch_d=60.0,
        atr=0.0015,
        bb_upper=1.0880,
        bb_middle=1.0850,
        bb_lower=1.0820,
        vwap=1.0852,
        support_levels=[1.0800, 1.0780],
        resistance_levels=[1.0900, 1.0920],
        swing_high=1.0910,
        swing_low=1.0790,
        fib_236=1.0825,
        fib_382=1.0840,
        fib_500=1.0850,
        fib_618=1.0860,
        fib_786=1.0875,
    )


class TestIndicatorsAPI:
    @pytest.mark.asyncio
    async def test_get_indicators_empty(self, client: AsyncClient, db_session):
        """GET /api/v1/indicators/{symbol} returns empty list when no data."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/indicators/EURUSD?timeframe=H1&limit=100",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "H1"
        assert data["count"] == 0
        assert data["indicators"] == []

    @pytest.mark.asyncio
    async def test_get_indicators_with_data(self, client: AsyncClient, db_session):
        """GET /api/v1/indicators/{symbol} returns indicator data."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = IndicatorRepository(db_session)
        for i in range(5):
            ind = make_indicator(ts_offset=i)
            await repo.upsert(ind)

        response = await client.get(
            "/api/v1/indicators/EURUSD?timeframe=H1&limit=100",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["indicators"]) == 5
        first = data["indicators"][0]
        assert first["rsi"] == 55.0
        assert first["ema_20"] == 1.0850

    @pytest.mark.asyncio
    async def test_get_indicators_invalid_symbol(self, client: AsyncClient, db_session):
        """Invalid symbol returns 404."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/indicators/INVALID?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_indicators_invalid_timeframe(self, client: AsyncClient, db_session):
        """Invalid timeframe returns 400."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/indicators/EURUSD?timeframe=INVALID",
            headers=headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_indicators_requires_auth(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/indicators/EURUSD?timeframe=H1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_latest_indicator(self, client: AsyncClient, db_session):
        """GET /api/v1/indicators/{symbol}/latest returns the latest indicator."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = IndicatorRepository(db_session)
        for i in range(3):
            ind = make_indicator(ts_offset=i)
            await repo.upsert(ind)

        response = await client.get(
            "/api/v1/indicators/EURUSD/latest?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        indicator = data["indicator"]
        assert indicator["symbol"] == "EURUSD"
        assert indicator["timeframe"] == "H1"
        assert indicator["rsi"] == 55.0

    @pytest.mark.asyncio
    async def test_get_latest_indicator_not_found(self, client: AsyncClient, db_session):
        """Latest indicator endpoint returns 404 when no data exists."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/indicators/EURUSD/latest?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_support_resistance(self, client: AsyncClient, db_session):
        """GET /api/v1/support-resistance/{symbol} returns S/R levels."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = IndicatorRepository(db_session)
        ind = make_indicator()
        await repo.upsert(ind)

        response = await client.get(
            "/api/v1/support-resistance/EURUSD?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["support_levels"] == [1.0800, 1.0780]
        assert data["resistance_levels"] == [1.0900, 1.0920]

    @pytest.mark.asyncio
    async def test_support_resistance_not_found(self, client: AsyncClient, db_session):
        """S/R endpoint returns 404 when no data exists."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/support-resistance/EURUSD?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_fibonacci(self, client: AsyncClient, db_session):
        """GET /api/v1/fibonacci/{symbol} returns Fibonacci levels."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = IndicatorRepository(db_session)
        ind = make_indicator()
        await repo.upsert(ind)

        response = await client.get(
            "/api/v1/fibonacci/EURUSD?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["fib_236"] == 1.0825
        assert data["fib_500"] == 1.0850
        assert data["fib_618"] == 1.0860

    @pytest.mark.asyncio
    async def test_fibonacci_not_found(self, client: AsyncClient, db_session):
        """Fibonacci endpoint returns 404 when no data exists."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/fibonacci/EURUSD?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404


class TestIndicatorRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, db_session):
        """Test basic upsert and retrieval."""
        repo = IndicatorRepository(db_session)
        ind = make_indicator()
        await repo.upsert(ind)

        result = await repo.get_by_symbol_timeframe("EURUSD", "H1", limit=10)
        assert len(result) == 1
        assert result[0].symbol == "EURUSD"
        assert result[0].rsi == 55.0

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db_session):
        """Test that upsert updates an existing row (same symbol+timeframe+timestamp)."""
        repo = IndicatorRepository(db_session)
        ind1 = make_indicator(ts_offset=0)
        await repo.upsert(ind1)

        # Create another with same symbol, timeframe, timestamp but different RSI
        ind2 = make_indicator(ts_offset=0)
        ind2.rsi = 70.0
        await repo.upsert(ind2)

        result = await repo.get_by_symbol_timeframe("EURUSD", "H1", limit=10)
        assert len(result) == 1
        assert result[0].rsi == 70.0

    @pytest.mark.asyncio
    async def test_exists(self, db_session):
        """Test exists check."""
        repo = IndicatorRepository(db_session)
        ind = make_indicator()
        await repo.upsert(ind)

        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert await repo.exists("EURUSD", "H1", base) is True
        assert await repo.exists("EURUSD", "H1", datetime.now(timezone.utc)) is False

    @pytest.mark.asyncio
    async def test_get_latest(self, db_session):
        """Test get_latest returns the most recent indicator."""
        repo = IndicatorRepository(db_session)
        for i in range(3):
            await repo.upsert(make_indicator(ts_offset=i))

        latest = await repo.get_latest("EURUSD", "H1")
        assert latest is not None
        # Compare timestamps ignoring tzinfo (SQLite strips timezone)
        expected_ts = make_indicator(ts_offset=2).timestamp
        assert latest.timestamp.replace(tzinfo=None) == expected_ts.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_get_range(self, db_session):
        """Test date range query."""
        repo = IndicatorRepository(db_session)
        for i in range(5):
            await repo.upsert(make_indicator(ts_offset=i))

        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        from_ts = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)  # ts_offset=1
        to_ts = datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc)    # ts_offset=3

        results = await repo.get_range("EURUSD", "H1", from_ts, to_ts)
        # Should include ts_offset 1, 2, 3
        assert len(results) == 3
