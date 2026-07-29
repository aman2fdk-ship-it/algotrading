from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Symbol ────────────────────────────────────────────────────────────────────

class SymbolResponse(BaseModel):
    code: str
    name: str
    asset_type: str
    pip_size: float
    digits: int
    enabled: bool

    model_config = {"from_attributes": True}


class SymbolListResponse(BaseModel):
    symbols: list[SymbolResponse]
    count: int


# ── Candle ────────────────────────────────────────────────────────────────────

class CandleResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    real_volume: int
    spread: int

    model_config = {"from_attributes": True}


class CandleListResponse(BaseModel):
    candles: list[CandleResponse]
    symbol: str
    timeframe: str
    count: int


# ── Tick ──────────────────────────────────────────────────────────────────────

class TickResponse(BaseModel):
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    spread: int
    volume: int

    model_config = {"from_attributes": True}


class TickListResponse(BaseModel):
    ticks: list[TickResponse]
    symbol: str
    count: int


# ── Price (latest) ────────────────────────────────────────────────────────────

class PriceResponse(BaseModel):
    symbol: str
    bid: float
    ask: float
    spread: int
    timestamp: datetime


# ── Account ───────────────────────────────────────────────────────────────────

class AccountResponse(BaseModel):
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    name: Optional[str] = None
    server: Optional[str] = None
    login: Optional[int] = None
    last_updated: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Broker ────────────────────────────────────────────────────────────────────

class BrokerResponse(BaseModel):
    name: str
    server: str
    timezone: str
    regulation: Optional[str] = None
    last_updated: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Market Status ─────────────────────────────────────────────────────────────

class MarketStatusResponse(BaseModel):
    symbol: str
    is_open: bool
    session: str
    last_updated: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketStatusListResponse(BaseModel):
    statuses: list[MarketStatusResponse]
    count: int
