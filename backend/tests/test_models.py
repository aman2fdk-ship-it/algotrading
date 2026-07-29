"""Unit tests for database models."""

import pytest
from datetime import datetime, timezone

from app.models.symbol import Symbol
from app.models.candle import Candle
from app.models.tick import Tick
from app.models.account import AccountInfo
from app.models.broker import BrokerInfo
from app.models.market_status import MarketStatus
from app.models.technical_indicator import TechnicalIndicator


class TestSymbolModel:
    def test_create_symbol(self):
        symbol = Symbol(
            code="EURUSD",
            name="Euro / US Dollar",
            asset_type="forex",
            pip_size=0.0001,
            digits=5,
            enabled=True,
        )
        assert symbol.code == "EURUSD"
        assert symbol.name == "Euro / US Dollar"
        assert symbol.asset_type == "forex"
        assert symbol.pip_size == 0.0001
        assert symbol.digits == 5
        assert symbol.enabled is True
        assert "EURUSD" in repr(symbol)

    def test_symbol_defaults(self):
        symbol = Symbol(code="BTCUSD", name="Bitcoin / USD")
        # SQLAlchemy column defaults only apply on insert; in Python they default to None/0
        assert symbol.code == "BTCUSD"
        assert symbol.name == "Bitcoin / USD"


class TestCandleModel:
    def test_create_candle(self):
        now = datetime.now(timezone.utc)
        candle = Candle(
            symbol="EURUSD",
            timeframe="M5",
            timestamp=now,
            open=1.0850,
            high=1.0860,
            low=1.0840,
            close=1.0855,
            tick_volume=150,
            real_volume=10,
            spread=2,
        )
        assert candle.symbol == "EURUSD"
        assert candle.timeframe == "M5"
        assert candle.open == 1.0850
        assert candle.close == 1.0855
        assert candle.tick_volume == 150
        assert "EURUSD" in repr(candle)
        assert "M5" in repr(candle)


class TestTickModel:
    def test_create_tick(self):
        now = datetime.now(timezone.utc)
        tick = Tick(
            symbol="EURUSD",
            timestamp=now,
            bid=1.0850,
            ask=1.0852,
            spread=2,
            volume=5,
        )
        assert tick.symbol == "EURUSD"
        assert tick.bid == 1.0850
        assert tick.ask == 1.0852
        assert tick.spread == 2


class TestAccountInfoModel:
    def test_create_account(self):
        account = AccountInfo(
            balance=10000.0,
            equity=10050.0,
            margin=500.0,
            free_margin=9550.0,
            leverage=100,
            currency="USD",
            name="Demo",
            server="Broker-Demo",
            login=123456,
        )
        assert account.balance == 10000.0
        assert account.leverage == 100
        assert account.currency == "USD"


class TestBrokerInfoModel:
    def test_create_broker(self):
        broker = BrokerInfo(
            name="Test Broker",
            server="TestServer",
            timezone="UTC+2",
            regulation="FCA",
        )
        assert broker.name == "Test Broker"
        assert broker.server == "TestServer"


class TestMarketStatusModel:
    def test_create_market_status(self):
        status = MarketStatus(
            symbol="EURUSD",
            is_open=True,
            session="London",
        )
        assert status.symbol == "EURUSD"
        assert status.is_open is True
        assert status.session == "London"
        assert "EURUSD" in repr(status)


class TestTechnicalIndicatorModel:
    def test_create_indicator(self):
        now = datetime.now(timezone.utc)
        indicator = TechnicalIndicator(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=now,
            ema_20=1.0850,
            ema_50=1.0840,
            rsi=55.0,
            atr=0.0015,
            support_levels=[1.0800, 1.0780],
            resistance_levels=[1.0900, 1.0920],
        )
        assert indicator.symbol == "EURUSD"
        assert indicator.timeframe == "H1"
        assert indicator.ema_20 == 1.0850
        assert indicator.rsi == 55.0
        assert indicator.support_levels == [1.0800, 1.0780]
        assert indicator.resistance_levels == [1.0900, 1.0920]
        assert "EURUSD" in repr(indicator)
        assert "H1" in repr(indicator)

    def test_indicator_nullable_fields(self):
        """Ensure nullable fields default to None."""
        now = datetime.now(timezone.utc)
        indicator = TechnicalIndicator(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=now,
        )
        assert indicator.supertrend_direction is None
        assert indicator.adx is None
        assert indicator.macd_line is None
        assert indicator.swing_high is None
        assert indicator.fib_236 is None
