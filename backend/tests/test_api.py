"""Integration tests for market data API endpoints."""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.models.user import User
from app.models.symbol import Symbol
from app.models.tick import Tick
from app.models.candle import Candle
from app.models.account import AccountInfo
from app.models.broker import BrokerInfo
from app.models.market_status import MarketStatus
from app.services.mt5_client import MockMT5Client, set_mt5_client


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSymbolsEndpoint:
    @pytest.mark.asyncio
    async def test_list_symbols_empty(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/symbols", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "symbols" in data
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_symbols_with_data(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        db_session.add(Symbol(code="EURUSD", name="Euro/USD", asset_type="forex", pip_size=0.0001, digits=5, enabled=True))
        db_session.add(Symbol(code="BTCUSD", name="Bitcoin/USD", asset_type="crypto", pip_size=1.0, digits=2, enabled=True))
        await db_session.flush()

        response = await client.get("/api/v1/symbols", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        codes = [s["code"] for s in data["symbols"]]
        assert "EURUSD" in codes
        assert "BTCUSD" in codes

    @pytest.mark.asyncio
    async def test_list_symbols_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/symbols")
        assert response.status_code == 401


class TestAccountEndpoint:
    @pytest.mark.asyncio
    async def test_get_account_from_db(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        account = AccountInfo(
            balance=5000, equity=5050, margin=250, free_margin=4800,
            leverage=50, currency="EUR", name="TestAcc", server="DemoSrv", login=999,
        )
        db_session.add(account)
        await db_session.flush()

        response = await client.get("/api/v1/account", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 5000
        assert data["currency"] == "EUR"
        assert data["leverage"] == 50


class TestBrokerEndpoint:
    @pytest.mark.asyncio
    async def test_get_broker_from_db(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        broker = BrokerInfo(
            name="TestBroker", server="TestSrv", timezone="UTC+3", regulation="FCA",
        )
        db_session.add(broker)
        await db_session.flush()

        response = await client.get("/api/v1/broker", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestBroker"
        assert data["timezone"] == "UTC+3"


class TestPriceEndpoint:
    @pytest.mark.asyncio
    async def test_get_price_from_db(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        now = datetime.now(timezone.utc)
        tick = Tick(symbol="EURUSD", timestamp=now, bid=1.0850, ask=1.0852, spread=2)
        db_session.add(tick)
        await db_session.flush()

        response = await client.get("/api/v1/price/EURUSD", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["bid"] == 1.0850
        assert data["ask"] == 1.0852

    @pytest.mark.asyncio
    async def test_get_price_unsupported_symbol(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/price/INVALID", headers=headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_price_no_data(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        # No tick data, and mock MT5 won't be connected
        response = await client.get("/api/v1/price/EURUSD", headers=headers)
        assert response.status_code in (404, 503)


class TestCandlesEndpoint:
    @pytest.mark.asyncio
    async def test_get_candles_with_data(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        now = datetime.now(timezone.utc)
        candle = Candle(
            symbol="EURUSD", timeframe="M5", timestamp=now,
            open=1.08, high=1.09, low=1.07, close=1.085,
            tick_volume=100, spread=2,
        )
        db_session.add(candle)
        await db_session.flush()

        response = await client.get("/api/v1/candles/EURUSD?timeframe=M5&limit=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "M5"
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_get_candles_invalid_timeframe(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/candles/EURUSD?timeframe=W1", headers=headers)
        assert response.status_code == 400


class TestTicksEndpoint:
    @pytest.mark.asyncio
    async def test_get_ticks_with_data(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        now = datetime.now(timezone.utc)
        tick = Tick(symbol="EURUSD", timestamp=now, bid=1.0850, ask=1.0852, spread=2)
        db_session.add(tick)
        await db_session.flush()

        response = await client.get("/api/v1/ticks/EURUSD?limit=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_get_ticks_unsupported_symbol(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/ticks/INVALID", headers=headers)
        assert response.status_code == 404


class TestMarketStatusEndpoint:
    @pytest.mark.asyncio
    async def test_get_all_status(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        db_session.add(MarketStatus(symbol="EURUSD", is_open=True, session="London"))
        db_session.add(MarketStatus(symbol="GBPUSD", is_open=False, session="closed"))
        await db_session.flush()

        response = await client.get("/api/v1/market-status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_get_symbol_status(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        db_session.add(MarketStatus(symbol="EURUSD", is_open=True, session="NY"))
        await db_session.flush()

        response = await client.get("/api/v1/market-status/EURUSD", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["session"] == "NY"

    @pytest.mark.asyncio
    async def test_get_symbol_status_not_found(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/market-status/EURUSD", headers=headers)
        assert response.status_code == 404
