"""Market Data Provider abstraction.

The rest of the application consumes live/quoted market data through a single
``MarketDataProvider`` interface instead of calling MetaTrader5 (or any other
vendor) directly.  This makes the market-data *source* pluggable:

- :class:`MarketDataProvider` — the interface/app-facing contract.
- :class:`MT5Provider` — an adapter that exposes the existing MT5 client family
  (real/mock) behind that interface, so MetaTrader5 stays a supported source.
- :class:`OandaProvider` — a broker REST feed (OANDA v20 practice-style: REST +
  demo account) driven entirely by environment variables.  It is the first
  first-class "real prices" provider and needs no hardcoded secrets.
- :func:`get_market_data_provider` — the factory the rest of the app and the
  tests wire through.  It selects the configured provider and, if a configured
  provider cannot be realised (e.g. OANDA creds missing/invalid), degrades
  gracefully to the mock source with a clear log line.

All implementations reuse the shared dataclasses (``TickData``, ``OHLCVData``,
``AccountData``, ``BrokerData``) defined in ``app.services.mt5_client``.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.config import Settings, settings as default_settings
from app.services.mt5_client import (
    AccountData,
    BrokerData,
    MT5ClientProtocol,
    OHLCVData,
    TickData,
)

logger = logging.getLogger(__name__)

# OANDA v20 hosts (see https://developer.oanda.com/rest-live-v20/introduction/)
OANDA_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# Map app timeframes to OANDA v20 candle granularity.
_TIMEFRAME_TO_OANDA_GRANULARITY = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
}


# ── Interface ─────────────────────────────────────────────────────────────────

class MarketDataProvider(ABC):
    """Pluggable market-data source interface.

    Deliberately aligns with the MT5 client surface so any MT5 client is a
    trivial adapter (see :class:`MT5Provider`) and broker REST feeds (see
    :class:`OandaProvider`) can expose the same contract.
    """

    @abstractmethod
    async def connect(self, **kwargs: Any) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

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

    @abstractmethod
    async def get_current_tick(self, symbol: str) -> TickData | None: ...

    @abstractmethod
    async def get_account_info(self) -> AccountData: ...

    @abstractmethod
    async def get_broker_info(self) -> BrokerData: ...


# ── MT5 Adapter ───────────────────────────────────────────────────────────────

class MT5Provider(MarketDataProvider):
    """Adapter exposing an existing MT5 client behind ``MarketDataProvider``.

    This keeps MetaTrader5 usable as a source without rebuilding the app, and
    it is also what carries the mock fallback (the factory wraps the selected
    mock client here).
    """

    def __init__(self, client: MT5ClientProtocol) -> None:
        self._client = client

    @property
    def client(self) -> MT5ClientProtocol:
        return self._client

    async def connect(self, **kwargs: Any) -> bool:
        return await self._client.connect(**kwargs)

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def is_connected(self) -> bool:
        return await self._client.is_connected()

    async def get_symbols(self) -> list[str]:
        return await self._client.get_symbols()

    async def subscribe_ticks(self, symbols: list[str], callback: Callable[[TickData], Any]) -> None:
        await self._client.subscribe_ticks(symbols, callback)

    async def fetch_ticks(self, symbol: str, count: int = 100) -> list[TickData]:
        return await self._client.fetch_ticks(symbol, count=count)

    async def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> list[OHLCVData]:
        return await self._client.fetch_candles(symbol, timeframe, count=count)

    async def heartbeat(self) -> bool:
        return await self._client.heartbeat()

    async def get_current_tick(self, symbol: str) -> TickData | None:
        return await self._client.get_current_tick(symbol)

    async def get_account_info(self) -> AccountData:
        return await self._client.get_account_info()

    async def get_broker_info(self) -> BrokerData:
        return await self._client.get_broker_info()


# ── OANDA (broker REST) Provider ──────────────────────────────────────────────

def _to_oanda_instrument(symbol: str) -> str:
    """Convert app symbol (EURUSD) to OANDA instrument (EUR_USD)."""
    sym = symbol.upper().replace("_", "")
    if len(sym) == 6:
        return f"{sym[:3]}_{sym[3:]}"
    return sym


def _from_oanda_instrument(instrument: str) -> str:
    return instrument.upper().replace("_", "")


def _parse_oanda_time(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _parse_leverage(value: str | None) -> int:
    if not value:
        return 100
    # OANDA reports leverage as e.g. "50:1"; take the ratio before the colon.
    head = str(value).split(":")[0]
    digits = "".join(ch for ch in head if ch.isdigit())
    return int(digits) if digits else 100


def _parse_login(value: Any) -> int | None:
    """Parse a numeric login from an OANDA account id.

    OANDA account IDs look like ``101-001-2345678-001`` and are not pure
    integers; ``AccountData.login`` is nullable so we extract any digits and
    return ``None`` when nothing usable is present rather than raising.
    """
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


class OandaProvider(MarketDataProvider):
    """OANDA v20 practice-style broker REST provider (env-driven only).

    No credentials are hardcoded or committed.  ``OandaProvider.from_settings``
    returns ``None`` when the required env vars are absent, which lets the
    factory fall back to the mock source (graceful degradation).
    """

    def __init__(
        self,
        api_key: str,
        account_id: str,
        base_url: str,
        timeout_s: float = 10.0,
        request_delay_s: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._account_id = account_id
        self._base_url = base_url.rstrip("/")
        self._timeout_s = float(timeout_s)
        self._request_delay_s = float(request_delay_s)
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._callbacks: dict[str, list[Callable]] = {}

    @classmethod
    def from_settings(cls, cfg: Settings) -> "OandaProvider | None":
        """Build a provider from settings, or ``None`` when not configured."""
        api_key = (cfg.OANDA_API_KEY or "").strip()
        account_id = (cfg.OANDA_ACCOUNT_ID or "").strip()
        if not api_key or not account_id:
            return None
        env = (cfg.OANDA_ENV or "practice").strip().lower() or "practice"
        base_url = (cfg.OANDA_BASE_URL or "").strip() or OANDA_HOSTS.get(env, OANDA_HOSTS["practice"])
        return cls(
            api_key=api_key,
            account_id=account_id,
            base_url=base_url,
            timeout_s=cfg.OANDA_TIMEOUT_S,
            request_delay_s=cfg.OANDA_REQUEST_DELAY_S,
        )

    # -- HTTP plumbing --------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "base_url": self._base_url,
                "headers": {"Authorization": f"Bearer {self._api_key}"},
                "timeout": self._timeout_s,
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict | None:
        if self._request_delay_s:
            await asyncio.sleep(self._request_delay_s)
        try:
            resp = await self._get_client().request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            logger.error("OANDA %s %s timed out: %s", method, path, exc)
            return None
        except httpx.HTTPError as exc:
            logger.error("OANDA %s %s error: %s", method, path, exc)
            return None
        if resp.status_code >= 400:
            logger.error(
                "OANDA %s %s returned HTTP %s: %s",
                method, path, resp.status_code, resp.text[:200],
            )
            return None
        try:
            return resp.json()
        except ValueError:
            logger.error("OANDA %s %s returned non-JSON body", method, path)
            return None

    # -- Connection lifecycle -------------------------------------------------

    async def connect(self, **kwargs: Any) -> bool:
        """Validate credentials by reading the account summary."""
        if not self._api_key or not self._account_id:
            logger.warning("OANDA provider not configured — cannot connect")
            return False
        try:
            data = await self._request("GET", f"/v3/accounts/{self._account_id}/summary")
        except Exception as exc:  # defensive: never let boot fail on a feed
            logger.error("OANDA connect error: %s", exc)
            return False
        if data is None:
            logger.error("OANDA connect failed: could not read account summary (check API key/account)")
            self._connected = False
            return False
        self._connected = True
        logger.info("OANDA provider connected (account %s)", self._account_id)
        return True

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        self._connected = False
        self._callbacks.clear()
        logger.info("OANDA provider disconnected")

    async def is_connected(self) -> bool:
        return self._connected

    async def heartbeat(self) -> bool:
        return self._connected

    # -- Symbols --------------------------------------------------------------

    async def get_symbols(self) -> list[str]:
        data = await self._request(
            "GET", f"/v3/accounts/{self._account_id}/instruments?instruments=all"
        )
        if not data:
            return []
        instruments = data.get("instruments") or []
        return [
            _from_oanda_instrument(str(instr.get("name", "")))
            for instr in instruments
            if instr.get("name")
        ]

    # -- Ticks / pricing ------------------------------------------------------

    @staticmethod
    def _price_to_tick(symbol: str, price: dict) -> TickData | None:
        bid = None
        ask = None
        for b in price.get("bids") or []:
            try:
                bid = float(b["price"])
                break
            except (KeyError, TypeError, ValueError):
                continue
        for a in price.get("asks") or []:
            try:
                ask = float(a["price"])
                break
            except (KeyError, TypeError, ValueError):
                continue
        closeout_bid = price.get("closeoutBid")
        closeout_ask = price.get("closeoutAsk")
        if closeout_bid is not None and closeout_bid != "":
            try:
                bid = float(closeout_bid)
            except ValueError:
                pass
        if closeout_ask is not None and closeout_ask != "":
            try:
                ask = float(closeout_ask)
            except ValueError:
                pass
        if bid is None or ask is None:
            return None
        spread = max(0, int(round((ask - bid) * 100000)))
        ts = _parse_oanda_time(price.get("time", "")) if price.get("time") else datetime.now(timezone.utc)
        return TickData(
            symbol=symbol,
            timestamp=ts,
            bid=bid,
            ask=ask,
            spread=spread,
            volume=0,
        )

    async def get_current_tick(self, symbol: str) -> TickData | None:
        instrument = _to_oanda_instrument(symbol)
        data = await self._request(
            "GET", f"/v3/accounts/{self._account_id}/pricing?instruments={instrument}"
        )
        if not data:
            return None
        prices = data.get("prices") or []
        if not prices:
            return None
        return self._price_to_tick(symbol, prices[0])

    async def fetch_ticks(self, symbol: str, count: int = 100) -> list[TickData]:
        """Return current/available pricing.

        OANDA v20 does not expose historical tick history over REST, so this
        returns at most the current tick (consistent with a live feed).
        """
        tick = await self.get_current_tick(symbol)
        return [tick] if tick else []

    # -- Candles --------------------------------------------------------------

    async def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> list[OHLCVData]:
        granularity = _TIMEFRAME_TO_OANDA_GRANULARITY.get(timeframe)
        if granularity is None:
            logger.error("Unsupported OANDA timeframe: %s", timeframe)
            return []
        instrument = _to_oanda_instrument(symbol)
        data = await self._request(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params={"granularity": granularity, "count": max(1, int(count))},
        )
        if not data:
            return []
        candles: list[OHLCVData] = []
        for c in data.get("candles") or []:
            mid = c.get("mid") or {}
            try:
                o = float(mid["o"]); h = float(mid["h"])
                lo = float(mid["l"]); cl = float(mid["c"])
            except (KeyError, TypeError, ValueError):
                continue
            ts = _parse_oanda_time(c["time"]) if c.get("time") else datetime.now(timezone.utc)
            candles.append(
                OHLCVData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=o,
                    high=h,
                    low=lo,
                    close=cl,
                    tick_volume=int(c.get("volume") or 0),
                    real_volume=0,
                )
            )
        return candles

    # -- Account / broker -----------------------------------------------------

    async def get_account_info(self) -> AccountData:
        data = await self._request("GET", f"/v3/accounts/{self._account_id}/summary")
        acc = (data or {}).get("account") or {}
        def _f(key: str, default: float = 0.0) -> float:
            try:
                return float(acc.get(key) or default)
            except (TypeError, ValueError):
                return default
        return AccountData(
            balance=_f("balance"),
            equity=_f("NAV"),
            margin=_f("marginUsed"),
            free_margin=_f("marginAvailable"),
            leverage=_parse_leverage(acc.get("leverage")),
            currency=acc.get("currency") or "USD",
            name=acc.get("alias") or "OANDA",
            server=acc.get("id") or self._account_id,
            login=_parse_login(acc.get("id") or self._account_id),
        )

    async def get_broker_info(self) -> BrokerData:
        data = await self._request("GET", f"/v3/accounts/{self._account_id}")
        acc = (data or {}).get("account") or {}
        return BrokerData(
            name=acc.get("alias") or "OANDA",
            server=acc.get("id") or self._account_id,
            timezone="UTC",
            regulation="OANDA (practice)",
        )

    # -- Subscription ---------------------------------------------------------

    async def subscribe_ticks(self, symbols: list[str], callback: Callable[[TickData], Any]) -> None:
        """Register interest in live ticks for symbols.

        The transaction engine polls ``get_current_tick`` (the tick collector
        path), so this merely records callbacks for the provider's bookkeeping.
        """
        for sym in symbols:
            if sym not in self._callbacks:
                self._callbacks[sym] = []
            self._callbacks[sym].append(callback)
        logger.info("OANDA provider: tick subscription registered for %d symbols", len(symbols))


# ── Factory ───────────────────────────────────────────────────────────────────

_provider: MarketDataProvider | None = None


def _mock_provider() -> MarketDataProvider:
    from app.services.mt5_client import MockMT5Client
    return MT5Provider(MockMT5Client())


def _mt5_provider(cfg: Settings | None = None) -> MarketDataProvider:
    from app.services.mt5_client import get_mt5_client
    client = get_mt5_client()
    if hasattr(client, "connect"):
        pass
    return MT5Provider(client)


def get_market_data_provider(cfg: Settings | None = None) -> MarketDataProvider:
    """Return the market-data provider selected by configuration.

    Selection rules:
      * MARKET_DATA_PROVIDER=oanda  -> OANDA; falls back to mock if creds absent.
      * MARKET_DATA_PROVIDER=mt5    -> MT5 path (real/mock as available).
      * MARKET_DATA_PROVIDER=mock   -> mock.
      * auto (default)              -> OANDA if creds present, else MT5 path if
                                       MT5_ENABLED, else mock; unrecognised
                                       values fall back to mock.
    """
    global _provider
    if _provider is not None:
        return _provider

    cfg = cfg or default_settings
    requested = (cfg.MARKET_DATA_PROVIDER or "auto").strip().lower()
    oanda = OandaProvider.from_settings(cfg)

    if requested == "oanda":
        if oanda is None:
            logger.warning(
                "MARKET_DATA_PROVIDER=oanda but OANDA credentials are missing "
                "(OANDA_API_KEY/OANDA_ACCOUNT_ID) — falling back to mock provider"
            )
            _provider = _mock_provider()
        else:
            logger.info("Using OANDA market data provider (practice REST feed)")
            _provider = oanda
        return _provider

    if requested == "mt5":
        logger.info("Using MT5 market data provider")
        _provider = _mt5_provider(cfg)
        return _provider

    if requested == "mock":
        logger.info("Using mock market data provider")
        _provider = _mock_provider()
        return _provider

    if requested == "auto":
        if oanda is not None:
            logger.info("Auto-selected OANDA market data provider")
            _provider = oanda
            return _provider
        if cfg.MT5_ENABLED:
            _provider = _mt5_provider(cfg)
        else:
            logger.info("No market data provider configured — using mock fallback")
            _provider = _mock_provider()
        return _provider

    logger.warning("Unknown MARKET_DATA_PROVIDER=%r — falling back to mock provider", requested)
    _provider = _mock_provider()
    return _provider


def set_market_data_provider(provider: MarketDataProvider) -> None:
    """Override the global provider (useful for testing/DI)."""
    global _provider
    _provider = provider


def reset_market_data_provider() -> None:
    """Clear the cached/overridden provider so selection re-runs (testing)."""
    global _provider
    _provider = None
