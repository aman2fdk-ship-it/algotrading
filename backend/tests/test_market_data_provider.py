"""Tests for the pluggable market-data provider abstraction.

Covers:
  * Factory selection / graceful mock fallback (``get_market_data_provider``).
  * OANDA REST provider behaviour via an ``httpx`` mock transport
    (request URL + auth header, JSON parsing, timeout/error handling,
    "not configured" -> mock fallback).
  * Interface conformance (mock / MT5 / OANDA all satisfy MarketDataProvider).
  * Router wire-up (``/api/v1/...`` serves against the provider).

These are unit/component tests (SQLite + mock transport) and do not require
live PG/Redis.  They follow the existing backend test conventions (conftest's
``setup_database`` autouse fixture, ``Settings`` constructed by field).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.config import Settings
from app.services.market_data_provider import (
    MarketDataProvider,
    MT5Provider,
    OandaProvider,
    _from_oanda_instrument,
    _mock_provider,
    _parse_oanda_time,
    _to_oanda_instrument,
    get_market_data_provider,
    reset_market_data_provider,
    set_market_data_provider,
)


# ── Helpers / fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_provider_singleton():
    """Ensure the provider factory singleton never leaks between tests."""
    reset_market_data_provider()
    yield
    reset_market_data_provider()


def _oanda_settings(**overrides) -> Settings:
    base = dict(
        MARKET_DATA_PROVIDER="oanda",
        OANDA_API_KEY="test-api-key",
        OANDA_ACCOUNT_ID="101-001-2345678-001",
        OANDA_ENV="practice",
        MT5_ENABLED=False,
    )
    base.update(overrides)
    return Settings(**base)


def _mock_transport(handler):
    """Build an httpx async transport that routes all requests to ``handler``."""
    return httpx.MockTransport(handler)


class StubProvider(MarketDataProvider):
    """Minimal deterministic provider for router wire-up tests."""

    def __init__(self):
        self._connected = True
        self._tick = None

    async def connect(self, **kwargs) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def get_symbols(self) -> list[str]:
        return ["EURUSD"]

    async def subscribe_ticks(self, symbols, callback) -> None:
        pass

    async def fetch_ticks(self, symbol, count=100) -> list:
        return [self._tick] if self._tick else []

    async def fetch_candles(self, symbol, timeframe, count=100) -> list:
        return []

    async def heartbeat(self) -> bool:
        return self._connected

    async def get_current_tick(self, symbol):
        from app.services.mt5_client import TickData
        return TickData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid=1.1000,
            ask=1.1001,
            spread=10,
        )

    async def get_account_info(self):
        from app.services.mt5_client import AccountData
        return AccountData(balance=10000.0, equity=10000.0)

    async def get_broker_info(self):
        from app.services.mt5_client import BrokerData
        return BrokerData(name="Stub", server="stub")


# ── Factory selection ─────────────────────────────────────────────────────────

def test_factory_auto_no_creds_no_mt5_falls_back_to_mock():
    cfg = Settings(MARKET_DATA_PROVIDER="auto", MT5_ENABLED=False)
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)
    assert isinstance(provider.client, type(_mock_provider().client))


def test_factory_explicit_mock():
    cfg = Settings(MARKET_DATA_PROVIDER="mock")
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)


def test_factory_oanda_creds_missing_falls_back_to_mock():
    # Explicitly request OANDA but no API key/account -> graceful mock fallback.
    cfg = Settings(MARKET_DATA_PROVIDER="oanda", MT5_ENABLED=False)
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)
    assert not isinstance(provider, OandaProvider)


def test_factory_oanda_with_creds_returns_oanda():
    cfg = _oanda_settings()
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, OandaProvider)


def test_factory_auto_with_oanda_creds_selects_oanda():
    cfg = Settings(
        MARKET_DATA_PROVIDER="auto",
        OANDA_API_KEY="k",
        OANDA_ACCOUNT_ID="101-001-0000000-001",
        MT5_ENABLED=True,
    )
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, OandaProvider)


def test_factory_auto_mt5_gated_by_mt5_enabled():
    # MT5 path only selected when MT5_ENABLED is on (and no OANDA creds).
    cfg = Settings(MARKET_DATA_PROVIDER="auto", MT5_ENABLED=True)
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)


def test_factory_auto_mt5_disabled_no_creds_falls_back_to_mock():
    cfg = Settings(MARKET_DATA_PROVIDER="auto", MT5_ENABLED=False)
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)
    assert not isinstance(provider, OandaProvider)


def test_factory_unknown_value_falls_back_to_mock():
    cfg = Settings(MARKET_DATA_PROVIDER="bogus-provider", MT5_ENABLED=False)
    provider = get_market_data_provider(cfg)
    assert isinstance(provider, MT5Provider)


def test_set_and_reset_provider():
    stub = StubProvider()
    set_market_data_provider(stub)
    assert get_market_data_provider() is stub
    reset_market_data_provider()
    # After reset, selection re-runs against default settings (auto, no creds).
    assert get_market_data_provider() is not stub


# ── Instrument / time helpers ─────────────────────────────────────────────────

def test_to_and_from_oanda_instrument():
    assert _to_oanda_instrument("EURUSD") == "EUR_USD"
    assert _to_oanda_instrument("XAUUSD") == "XAU_USD"
    assert _to_oanda_instrument("EUR_USD") == "EUR_USD"
    assert _from_oanda_instrument("EUR_USD") == "EURUSD"
    assert _from_oanda_instrument("EURUSD") == "EURUSD"


def test_parse_oanda_time_z_suffix():
    parsed = _parse_oanda_time("2024-01-15T10:30:00.123456789Z")
    assert parsed.year == 2024
    assert parsed.month == 1
    assert parsed.day == 15
    assert parsed.hour == 10
    assert parsed.minute == 30
    assert parsed.tzinfo is not None


def test_parse_oanda_time_offsets():
    parsed = _parse_oanda_time("2024-01-15T10:30:00+02:00")
    assert parsed.utcoffset().total_seconds() == 7200


# ── OANDA provider (mock transport) ──────────────────────────────────────────

def _account_summary_response():
    return {
        "account": {
            "id": "101-001-2345678-001",
            "alias": "Practice Account",
            "currency": "USD",
            "balance": "12345.67",
            "NAV": "12345.67",
            "marginUsed": "0",
            "marginAvailable": "12345.67",
            "leverage": "50:1",
        }
    }


def test_oanda_from_settings_missing_creds_returns_none():
    cfg = Settings(MARKET_DATA_PROVIDER="oanda", MT5_ENABLED=False)
    assert OandaProvider.from_settings(cfg) is None


def test_oanda_from_settings_with_creds_returns_provider():
    cfg = _oanda_settings()
    provider = OandaProvider.from_settings(cfg)
    assert provider is not None


def test_oanda_from_settings_env_and_base_url():
    cfg = _oanda_settings(OANDA_ENV="live")
    provider = OandaProvider.from_settings(cfg)
    assert provider is not None
    assert provider._base_url == "https://api-fxtrade.oanda.com"


def test_oanda_connect_sends_auth_header_and_url():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_account_summary_response())

    provider = OandaProvider(
        api_key="secret-key-123",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    connected = pytest_async_connect(provider)
    assert connected is True
    assert captured["auth"] == "Bearer secret-key-123"
    assert "/v3/accounts/" in captured["url"]
    assert captured["url"].endswith("/summary")
    assert captured["url"].startswith("https://api-fxpractice.oanda.com")


def test_oanda_connect_http_401_returns_false():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errorMessage": "Invalid token"})

    provider = OandaProvider(
        api_key="bad",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    assert pytest_async_connect(provider) is False
    assert pytest_async_is_connected(provider) is False


def test_oanda_get_current_tick_parses_pricing():
    pricing = {
        "prices": [
            {
                "instrument": "EUR_USD",
                "time": "2024-01-15T10:30:00.123456789Z",
                "bids": [{"price": "1.10000", "liquidity": 1000000}],
                "asks": [{"price": "1.10010", "liquidity": 1000000}],
                "closeoutBid": "1.09990",
                "closeoutAsk": "1.10020",
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pricing)

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    tick = pytest_async_get_current_tick(provider, "EURUSD")
    assert tick is not None
    assert tick.symbol == "EURUSD"
    assert tick.bid == 1.09990  # closeoutBid overrides first bid
    assert tick.ask == 1.10020  # closeoutAsk overrides first ask
    assert tick.spread == 30  # round((1.10020 - 1.09990) * 100000)
    assert tick.timestamp is not None


def test_oanda_get_current_tick_missing_prices_returns_none():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"prices": []})

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    assert pytest_async_get_current_tick(provider, "EURUSD") is None


def test_oanda_fetch_candles_parses_candles():
    candles = {
        "candles": [
            {
                "time": "2024-01-15T10:30:00.000000000Z",
                "volume": 1234,
                "mid": {"o": "1.1000", "h": "1.1005", "l": "1.0998", "c": "1.1003"},
            },
            {
                "time": "2024-01-15T10:31:00.000000000Z",
                "volume": 900,
                "mid": {"o": "1.1003", "h": "1.1009", "l": "1.1002", "c": "1.1008"},
            },
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "granularity=M5" in str(request.url)
        return httpx.Response(200, json=candles)

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    rows = pytest_async_fetch_candles(provider, "EURUSD", "M5")
    assert len(rows) == 2
    first = rows[0]
    assert first.symbol == "EURUSD"
    assert first.timeframe == "M5"
    assert first.open == 1.1000
    assert first.high == 1.1005
    assert first.low == 1.0998
    assert first.close == 1.1003
    assert first.tick_volume == 1234
    assert first.timestamp is not None


def test_oanda_fetch_candles_unsupported_timeframe_returns_empty():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["called"] = True
        return httpx.Response(200, json={"candles": []})

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    assert pytest_async_fetch_candles(provider, "EURUSD", "W1") == []
    assert "called" not in captured  # no request made for unsupported granularity


def test_oanda_get_symbols_parses_instruments():
    data = {
        "instruments": [
            {"name": "EUR_USD"},
            {"name": "GBP_USD"},
            {"name": "XAU_USD"},
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    symbols = pytest_async_get_symbols(provider)
    assert symbols == ["EURUSD", "GBPUSD", "XAUUSD"]


def test_oanda_timeout_returns_none_gracefully():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    assert pytest_async_connect(provider) is False
    assert pytest_async_get_current_tick(provider, "EURUSD") is None


def test_oanda_http_error_returns_none_gracefully():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    assert pytest_async_get_current_tick(provider, "EURUSD") is None


def test_oanda_account_info_parsing():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_account_summary_response())

    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
        transport=_mock_transport(handler),
    )
    info = pytest_async_get_account_info(provider)
    assert info.balance == 12345.67
    assert info.equity == 12345.67
    assert info.currency == "USD"
    assert info.leverage == 50


# ── Interface conformance ─────────────────────────────────────────────────────

def test_mock_provider_satisfies_market_data_provider_interface():
    provider = _mock_provider()
    assert isinstance(provider, MarketDataProvider)


def test_oanda_provider_satisfies_market_data_provider_interface():
    provider = OandaProvider(
        api_key="k",
        account_id="101-001-2345678-001",
        base_url="https://api-fxpractice.oanda.com",
    )
    assert isinstance(provider, MarketDataProvider)


def test_mt5_provider_satisfies_market_data_provider_interface():
    from app.services.mt5_client import MockMT5Client
    provider = MT5Provider(MockMT5Client())
    assert isinstance(provider, MarketDataProvider)
    assert isinstance(provider.client, MockMT5Client)


# ── Router wire-up ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_router_serves_price_against_set_provider(client, auth_headers):
    """The market-data router resolves requests through the provider."""
    from app.services.mt5_client import SUPPORTED_SYMBOLS

    set_market_data_provider(StubProvider())
    resp = await client.get(
        f"/api/v1/price/{SUPPORTED_SYMBOLS[0]}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bid"] == 1.1000
    assert body["ask"] == 1.1001


# ── asyncio sync-helper wrappers ──────────────────────────────────────────────

def pytest_async_connect(provider) -> bool:
    import asyncio
    return asyncio.run(provider.connect())


def pytest_async_is_connected(provider) -> bool:
    import asyncio
    return asyncio.run(provider.is_connected())


def pytest_async_get_current_tick(provider, symbol):
    import asyncio
    return asyncio.run(provider.get_current_tick(symbol))


def pytest_async_fetch_candles(provider, symbol, timeframe):
    import asyncio
    return asyncio.run(provider.fetch_candles(symbol, timeframe))


def pytest_async_fetch_ticks(provider, symbol):
    import asyncio
    return asyncio.run(provider.fetch_ticks(symbol))


def pytest_async_get_symbols(provider):
    import asyncio
    return asyncio.run(provider.get_symbols())


def pytest_async_get_account_info(provider):
    import asyncio
    return asyncio.run(provider.get_account_info())
