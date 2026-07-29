"""MT5 Client Wrapper — provides a clean abstraction over the MetaTrader5 package.

The real MetaTrader5 Python package is only available on Windows with MT5 installed.
This module provides:
- RealMT5Client: wraps the actual MetaTrader5 package (conditional import)
- MockMT5Client: mock implementation for development/testing
- MT5ClientProtocol: protocol/interface definition
- get_mt5_client(): factory function that returns the best available client
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
    "USDCAD", "USDCHF", "XAUUSD", "BTCUSD", "ETHUSD",
]

SUPPORTED_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

TIMEFRAME_MAP: dict[str, Any] = {}
try:
    import MetaTrader5 as _mt5
    HAS_MT5 = True
    TIMEFRAME_MAP = {
        "M1": _mt5.TIMEFRAME_M1,
        "M5": _mt5.TIMEFRAME_M5,
        "M15": _mt5.TIMEFRAME_M15,
        "M30": _mt5.TIMEFRAME_M30,
        "H1": _mt5.TIMEFRAME_H1,
        "H4": _mt5.TIMEFRAME_H4,
        "D1": _mt5.TIMEFRAME_D1,
    }
except ImportError:
    HAS_MT5 = False
    logger.warning("MetaTrader5 package not available — using mock client")


# ── Data Classes ──────────────────────────────────────────────────────────────

class TickDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass
class TickData:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    spread: int = 0
    volume: int = 0


@dataclass
class OHLCVData:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    real_volume: int = 0
    spread: int = 0


@dataclass
class AccountData:
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    leverage: int = 100
    currency: str = "USD"
    name: str | None = None
    server: str | None = None
    login: int | None = None


@dataclass
class BrokerData:
    name: str = "Unknown"
    server: str = "Unknown"
    timezone: str = "UTC"
    regulation: str | None = None


# ── Protocol / Interface ─────────────────────────────────────────────────────

class MT5ClientProtocol(ABC):
    """Abstract interface for MT5 clients."""

    @abstractmethod
    async def connect(self, path: str | None = None, **kwargs) -> bool: ...
    @abstractmethod
    async def disconnect(self) -> None: ...
    @abstractmethod
    async def is_connected(self) -> bool: ...
    @abstractmethod
    async def get_account_info(self) -> AccountData: ...
    @abstractmethod
    async def get_broker_info(self) -> BrokerData: ...
    @abstractmethod
    async def get_symbols(self) -> list[str]: ...
    @abstractmethod
    async def subscribe_ticks(self, symbols: list[str], callback: Callable[[TickData], Any]) -> None: ...
    @abstractmethod
    async def fetch_ticks(self, symbol: str, count: int = 100) -> list[TickData]: ...
    @abstractmethod
    async def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> list[OHLCVData]: ...
    @abstractmethod
    async def heartbeat(self) -> bool: ...


# ── Real MT5 Client ──────────────────────────────────────────────────────────

class RealMT5Client(MT5ClientProtocol):
    """Production MT5 client using the MetaTrader5 package."""

    def __init__(self) -> None:
        if not HAS_MT5:
            raise RuntimeError("MetaTrader5 package is not available")
        self._connected = False
        self._callbacks: dict[str, list[Callable]] = {}
        self._mt5 = _mt5

    async def connect(self, path: str | None = None, **kwargs) -> bool:
        """Connect to MT5 terminal. Auto-detects installation if no path given."""
        logger.info("Connecting to MT5 terminal...")
        try:
            if path:
                initialized = self._mt5.initialize(path=path, **kwargs)
            else:
                initialized = self._mt5.initialize(**kwargs)

            if initialized:
                self._connected = True
                version = self._mt5.version()
                logger.info(f"MT5 connected — version {version[0]}.{version[1]}, build {version[2]}")
                return True
            else:
                error = self._mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                self._connected = False
                return False
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        logger.info("Disconnecting from MT5...")
        self._mt5.shutdown()
        self._connected = False
        self._callbacks.clear()
        logger.info("MT5 disconnected")

    async def is_connected(self) -> bool:
        if not self._connected:
            return False
        try:
            terminal_info = self._mt5.terminal_info()
            return terminal_info is not None and terminal_info.connected
        except Exception:
            return False

    async def get_account_info(self) -> AccountData:
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError("Failed to retrieve account info")
        return AccountData(
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            leverage=info.leverage,
            currency=info.currency,
            name=info.name,
            server=info.server,
            login=info.login,
        )

    async def get_broker_info(self) -> BrokerData:
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError("Failed to retrieve broker info")
        return BrokerData(
            name=info.company or "Unknown",
            server=info.server or "Unknown",
            timezone="UTC",
        )

    async def get_symbols(self) -> list[str]:
        symbols = self._mt5.symbols_get()
        return [s.name for s in symbols] if symbols else []

    async def subscribe_ticks(self, symbols: list[str], callback: Callable[[TickData], Any]) -> None:
        """Subscribe to live ticks for the given symbols."""
        # MT5 doesn't have a push-based tick subscription in Python API
        # We use polling via symbol_info_tick in the tick collector service
        logger.info(f"Tick subscription registered for {len(symbols)} symbols")
        for sym in symbols:
            if sym not in self._callbacks:
                self._callbacks[sym] = []
            self._callbacks[sym].append(callback)

    async def fetch_ticks(self, symbol: str, count: int = 100) -> list[TickData]:
        ticks = self._mt5.copy_ticks_from(symbol, datetime.now(), count, self._mt5.COPY_TICKS_ALL)
        if ticks is None:
            return []
        results = []
        for t in ticks:
            results.append(TickData(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(t.time, tz=timezone.utc),
                bid=t.bid,
                ask=t.ask,
                spread=t.spread if hasattr(t, 'spread') else 0,
                volume=t.volume if hasattr(t, 'volume') else 0,
            ))
        return results

    async def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> list[OHLCVData]:
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            return []
        results = []
        for r in rates:
            results.append(OHLCVData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(r.time, tz=timezone.utc),
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                tick_volume=r.tick_volume,
                real_volume=r.real_volume if hasattr(r, 'real_volume') else 0,
                spread=r.spread,
            ))
        return results

    async def heartbeat(self) -> bool:
        return await self.is_connected()

    async def get_current_tick(self, symbol: str) -> TickData | None:
        """Poll current tick for a symbol."""
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return TickData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
            bid=tick.bid,
            ask=tick.ask,
            spread=tick.spread if hasattr(tick, 'spread') else 0,
            volume=0,
        )


# ── Mock MT5 Client ──────────────────────────────────────────────────────────

class MockMT5Client(MT5ClientProtocol):
    """Mock MT5 client for development and testing. Generates simulated data."""

    def __init__(self, base_prices: dict[str, float] | None = None) -> None:
        import random
        self._random = random
        self._connected = False
        self._base_prices = base_prices or {
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "USDJPY": 154.50,
            "AUDUSD": 0.6550,
            "NZDUSD": 0.5950,
            "USDCAD": 1.3650,
            "USDCHF": 0.8850,
            "XAUUSD": 2350.00,
            "BTCUSD": 67000.00,
            "ETHUSD": 3450.00,
        }
        self._current_prices = dict(self._base_prices)
        self._callbacks: dict[str, list[Callable]] = {}
        self._tick_counter: dict[str, int] = {s: 0 for s in SUPPORTED_SYMBOLS}

    async def connect(self, path: str | None = None, **kwargs) -> bool:
        logger.info("MockMT5: Connected (simulated)")
        self._connected = True
        return True

    async def disconnect(self) -> None:
        logger.info("MockMT5: Disconnected")
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def get_account_info(self) -> AccountData:
        return AccountData(
            balance=10000.0,
            equity=10050.0,
            margin=500.0,
            free_margin=9550.0,
            leverage=100,
            currency="USD",
            name="Demo Account",
            server="MockBroker-Demo",
            login=12345678,
        )

    async def get_broker_info(self) -> BrokerData:
        return BrokerData(
            name="Mock Broker Inc.",
            server="MockBroker-Demo",
            timezone="UTC+0",
            regulation="Mock Regulatory Authority",
        )

    async def get_symbols(self) -> list[str]:
        return list(SUPPORTED_SYMBOLS)

    async def subscribe_ticks(self, symbols: list[str], callback: Callable[[TickData], Any]) -> None:
        for sym in symbols:
            if sym not in self._callbacks:
                self._callbacks[sym] = []
            self._callbacks[sym].append(callback)
        logger.info(f"MockMT5: Subscribed to {len(symbols)} symbols")

    async def fetch_ticks(self, symbol: str, count: int = 100) -> list[TickData]:
        if symbol not in self._base_prices:
            return []
        base = self._base_prices[symbol]
        ticks = []
        now = datetime.now(timezone.utc)
        for i in range(count):
            ts = datetime.fromtimestamp(now.timestamp() - (count - i) * 0.5, tz=timezone.utc)
            price = base + self._random.uniform(-0.001, 0.001) * base * 0.01
            ticks.append(TickData(
                symbol=symbol,
                timestamp=ts,
                bid=round(price - 0.0001, 5),
                ask=round(price + 0.0001, 5),
                spread=2,
                volume=self._random.randint(1, 20),
            ))
        return ticks

    async def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> list[OHLCVData]:
        if symbol not in self._base_prices:
            return []
        base = self._base_prices[symbol]
        candles = []
        now = datetime.now(timezone.utc)
        # Approximate seconds per timeframe
        tf_seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
        step = tf_seconds.get(timeframe, 3600)
        for i in range(count):
            ts = datetime.fromtimestamp(now.timestamp() - (count - i) * step, tz=timezone.utc)
            o = base + self._random.uniform(-0.002, 0.002) * base * 0.01
            c = o + self._random.uniform(-0.001, 0.001) * base * 0.01
            h = max(o, c) + abs(self._random.uniform(0, 0.001)) * base * 0.01
            l = min(o, c) - abs(self._random.uniform(0, 0.001)) * base * 0.01
            candles.append(OHLCVData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=round(o, 5),
                high=round(h, 5),
                low=round(l, 5),
                close=round(c, 5),
                tick_volume=self._random.randint(50, 500),
                spread=2,
            ))
        return candles

    async def heartbeat(self) -> bool:
        return self._connected

    async def get_current_tick(self, symbol: str) -> TickData | None:
        """Generate a simulated current tick."""
        if symbol not in self._base_prices:
            return None
        base = self._current_prices.setdefault(symbol, self._base_prices[symbol])
        # Slight price movement
        base = base + self._random.uniform(-0.00002, 0.00002) * base * 0.01
        self._current_prices[symbol] = base
        return TickData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid=round(base - 0.0001, 5),
            ask=round(base + 0.0001, 5),
            spread=2,
            volume=self._random.randint(1, 10),
        )


# ── Factory Function ─────────────────────────────────────────────────────────

_mt5_client: MT5ClientProtocol | None = None


def get_mt5_client() -> MT5ClientProtocol:
    """Return the global MT5 client instance (real or mock)."""
    global _mt5_client
    if _mt5_client is None:
        if HAS_MT5:
            logger.info("Creating RealMT5Client")
            _mt5_client = RealMT5Client()
        else:
            logger.info("Creating MockMT5Client (MetaTrader5 package not available)")
            _mt5_client = MockMT5Client()
    return _mt5_client


def set_mt5_client(client: MT5ClientProtocol) -> None:
    """Override the global MT5 client (useful for testing)."""
    global _mt5_client
    _mt5_client = client
