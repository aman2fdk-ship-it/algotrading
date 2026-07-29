"""Unit tests for services."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.mt5_client import (
    MockMT5Client, get_mt5_client, set_mt5_client,
    SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES,
    TickData, OHLCVData, AccountData, BrokerData,
)
from app.services.tick_collector import LiveTickCollector
from app.services.candle_sync import CandleSynchronizer
from app.services.session_detector import SessionDetector
from app.services.market_status import MarketStatusMonitor
from app.services.reconnection import ReconnectionManager


class TestMockMT5Client:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        client = MockMT5Client()
        assert await client.is_connected() is False

        connected = await client.connect()
        assert connected is True
        assert await client.is_connected() is True

        await client.disconnect()
        assert await client.is_connected() is False

    @pytest.mark.asyncio
    async def test_get_account_info(self):
        client = MockMT5Client()
        await client.connect()

        account = await client.get_account_info()
        assert account.balance == 10000.0
        assert account.equity == 10050.0
        assert account.leverage == 100
        assert account.currency == "USD"

    @pytest.mark.asyncio
    async def test_get_broker_info(self):
        client = MockMT5Client()
        await client.connect()

        broker = await client.get_broker_info()
        assert broker.name == "Mock Broker Inc."
        assert broker.server == "MockBroker-Demo"

    @pytest.mark.asyncio
    async def test_get_symbols(self):
        client = MockMT5Client()
        await client.connect()

        symbols = await client.get_symbols()
        assert len(symbols) == 10
        assert "EURUSD" in symbols
        assert "BTCUSD" in symbols

    @pytest.mark.asyncio
    async def test_fetch_ticks(self):
        client = MockMT5Client()
        await client.connect()

        ticks = await client.fetch_ticks("EURUSD", count=10)
        assert len(ticks) == 10
        assert all(t.symbol == "EURUSD" for t in ticks)
        assert all(t.bid > 0 for t in ticks)

    @pytest.mark.asyncio
    async def test_fetch_candles(self):
        client = MockMT5Client()
        await client.connect()

        candles = await client.fetch_candles("EURUSD", "M5", count=10)
        assert len(candles) == 10
        assert all(c.symbol == "EURUSD" for c in candles)
        assert all(c.high >= c.low for c in candles)

    @pytest.mark.asyncio
    async def test_fetch_unknown_symbol(self):
        client = MockMT5Client()
        await client.connect()

        ticks = await client.fetch_ticks("INVALID", count=10)
        assert ticks == []

        candles = await client.fetch_candles("INVALID", "M5", count=10)
        assert candles == []

    @pytest.mark.asyncio
    async def test_get_current_tick(self):
        client = MockMT5Client()
        await client.connect()

        tick = await client.get_current_tick("EURUSD")
        assert tick is not None
        assert tick.symbol == "EURUSD"
        assert tick.bid > 0


class TestSessionDetector:
    def test_determine_session_asian(self):
        assert SessionDetector._determine_session(1) == "Asian"
        assert SessionDetector._determine_session(5) == "Asian"

    def test_determine_session_london(self):
        assert SessionDetector._determine_session(9) == "London"
        assert SessionDetector._determine_session(12) == "London"

    def test_determine_session_london_ny(self):
        assert SessionDetector._determine_session(14) == "London/NY"
        assert SessionDetector._determine_session(16) == "London/NY"

    def test_determine_session_ny(self):
        assert SessionDetector._determine_session(18) == "NY"
        assert SessionDetector._determine_session(20) == "NY"

    def test_determine_session_closed(self):
        assert SessionDetector._determine_session(22) == "closed"
        assert SessionDetector._determine_session(23) == "closed"


class TestReconnectionManager:
    @pytest.mark.asyncio
    async def test_stats_initial(self):
        client = MockMT5Client()
        rm = ReconnectionManager(client)
        stats = rm.stats
        assert stats["consecutive_failures"] == 0
        assert stats["total_disconnections"] == 0
