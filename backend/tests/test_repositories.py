"""Unit tests for repositories."""

import pytest
from datetime import datetime, timezone

from app.models.symbol import Symbol
from app.models.candle import Candle
from app.models.tick import Tick
from app.models.account import AccountInfo
from app.models.broker import BrokerInfo
from app.models.market_status import MarketStatus
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.tick_repository import TickRepository
from app.repositories.account_repository import AccountRepository
from app.repositories.broker_repository import BrokerRepository
from app.repositories.market_status_repository import MarketStatusRepository


class TestSymbolRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_all(self, db_session):
        repo = SymbolRepository(db_session)

        symbol = Symbol(code="EURUSD", name="Euro/USD", asset_type="forex", pip_size=0.0001, digits=5, enabled=True)
        await repo.upsert(symbol)

        all_symbols = await repo.get_all()
        assert len(all_symbols) == 1
        assert all_symbols[0].code == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_by_code(self, db_session):
        repo = SymbolRepository(db_session)

        symbol = Symbol(code="GBPUSD", name="Pound/USD", asset_type="forex", pip_size=0.0001, digits=5, enabled=True)
        await repo.upsert(symbol)

        found = await repo.get_by_code("GBPUSD")
        assert found is not None
        assert found.name == "Pound/USD"

        not_found = await repo.get_by_code("NONEXIST")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db_session):
        repo = SymbolRepository(db_session)

        await repo.upsert(Symbol(code="EURUSD", name="Euro/USD", asset_type="forex", pip_size=0.0001, digits=5, enabled=True))
        await repo.upsert(Symbol(code="EURUSD", name="Euro / US Dollar Updated", asset_type="forex", pip_size=0.0001, digits=5, enabled=True))

        found = await repo.get_by_code("EURUSD")
        assert found.name == "Euro / US Dollar Updated"

        all_s = await repo.get_all()
        assert len(all_s) == 1  # No duplicates

    @pytest.mark.asyncio
    async def test_get_enabled(self, db_session):
        repo = SymbolRepository(db_session)

        await repo.upsert(Symbol(code="EURUSD", name="E", asset_type="forex", pip_size=0.0001, digits=5, enabled=True))
        await repo.upsert(Symbol(code="GBPUSD", name="G", asset_type="forex", pip_size=0.0001, digits=5, enabled=False))

        enabled = await repo.get_enabled()
        assert len(enabled) == 1
        assert enabled[0].code == "EURUSD"


class TestCandleRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_candles(self, db_session):
        repo = CandleRepository(db_session)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        candle1 = Candle(
            symbol="EURUSD", timeframe="M5", timestamp=now,
            open=1.08, high=1.09, low=1.07, close=1.085,
            tick_volume=100, spread=2,
        )
        await repo.upsert_candle(candle1)

        candles = await repo.get_candles("EURUSD", "M5", limit=10)
        assert len(candles) == 1
        assert candles[0].symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db_session):
        repo = CandleRepository(db_session)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        c1 = Candle(
            symbol="EURUSD", timeframe="M5", timestamp=now,
            open=1.08, high=1.09, low=1.07, close=1.085,
            tick_volume=100, spread=2,
        )
        await repo.upsert_candle(c1)

        c2 = Candle(
            symbol="EURUSD", timeframe="M5", timestamp=now,
            open=1.08, high=1.10, low=1.06, close=1.09,
            tick_volume=200, real_volume=0, spread=2,
        )
        await repo.upsert_candle(c2)

        candles = await repo.get_candles("EURUSD", "M5", limit=10)
        assert len(candles) == 1
        assert candles[0].high == 1.10
        assert candles[0].tick_volume == 200

    @pytest.mark.asyncio
    async def test_get_latest_candle(self, db_session):
        repo = CandleRepository(db_session)
        t1 = datetime(2024, 1, 1, 12, 0, 0)
        t2 = datetime(2024, 1, 1, 12, 5, 0)

        await repo.upsert_candle(Candle(
            symbol="EURUSD", timeframe="M5", timestamp=t1,
            open=1.08, high=1.09, low=1.07, close=1.085,
            tick_volume=100, spread=2,
        ))
        await repo.upsert_candle(Candle(
            symbol="EURUSD", timeframe="M5", timestamp=t2,
            open=1.085, high=1.09, low=1.08, close=1.088,
            tick_volume=150, spread=2,
        ))

        latest = await repo.get_latest_candle("EURUSD", "M5")
        assert latest is not None
        assert latest.timestamp == t2
        assert latest.close == 1.088


class TestTickRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_ticks(self, db_session):
        repo = TickRepository(db_session)
        now = datetime.now(timezone.utc)

        tick = Tick(
            symbol="EURUSD", timestamp=now,
            bid=1.0850, ask=1.0852, spread=2, volume=5,
        )
        await repo.upsert_tick(tick)

        ticks = await repo.get_ticks("EURUSD", limit=10)
        assert len(ticks) == 1
        assert ticks[0].bid == 1.0850

    @pytest.mark.asyncio
    async def test_get_latest_tick(self, db_session):
        repo = TickRepository(db_session)
        t1 = datetime(2024, 1, 1, 12, 0, 0)
        t2 = datetime(2024, 1, 1, 12, 0, 1)

        await repo.upsert_tick(Tick(symbol="EURUSD", timestamp=t1, bid=1.0800, ask=1.0802, spread=2))
        await repo.upsert_tick(Tick(symbol="EURUSD", timestamp=t2, bid=1.0810, ask=1.0812, spread=2))

        latest = await repo.get_latest_tick("EURUSD")
        assert latest is not None
        assert latest.bid == 1.0810


class TestAccountRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_latest(self, db_session):
        repo = AccountRepository(db_session)

        await repo.upsert_account(10000, 10050, 500, 9550, 100, "USD", "Demo", "Server1", 123)
        await repo.upsert_account(20000, 20100, 1000, 19100, 200, "EUR", "Demo2", "Server2", 456)

        latest = await repo.get_latest()
        assert latest is not None
        assert latest.balance == 20000
        assert latest.currency == "EUR"


class TestBrokerRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_latest(self, db_session):
        repo = BrokerRepository(db_session)

        await repo.upsert_broker("BrokerA", "SrvA", "UTC+1", "FCA")
        await repo.upsert_broker("BrokerB", "SrvB", "UTC+2", "CySEC")

        latest = await repo.get_latest()
        assert latest is not None
        assert latest.name == "BrokerB"


class TestMarketStatusRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get_all(self, db_session):
        repo = MarketStatusRepository(db_session)

        await repo.upsert_status("EURUSD", True, "London")
        await repo.upsert_status("GBPUSD", False, "closed")

        all_status = await repo.get_all()
        assert len(all_status) == 2

    @pytest.mark.asyncio
    async def test_get_by_symbol(self, db_session):
        repo = MarketStatusRepository(db_session)

        await repo.upsert_status("EURUSD", True, "London")

        status = await repo.get_by_symbol("EURUSD")
        assert status is not None
        assert status.is_open is True
        assert status.session == "London"

        not_found = await repo.get_by_symbol("NZDUSD")
        assert not_found is None
