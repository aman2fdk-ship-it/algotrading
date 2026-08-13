"""Schemas for Technical Indicator API responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IndicatorResponse(BaseModel):
    """Full technical indicator data for one candle."""

    symbol: str
    timeframe: str
    timestamp: datetime

    # Trend
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    supertrend_direction: Optional[int] = None
    supertrend_value: Optional[float] = None
    adx: Optional[float] = None

    # Momentum
    rsi: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None

    # Volatility
    atr: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None

    # Volume
    vwap: Optional[float] = None

    # Price Action
    support_levels: Optional[list[float]] = None
    resistance_levels: Optional[list[float]] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    fib_236: Optional[float] = None
    fib_382: Optional[float] = None
    fib_500: Optional[float] = None
    fib_618: Optional[float] = None
    fib_786: Optional[float] = None

    model_config = {"from_attributes": True}


class IndicatorListResponse(BaseModel):
    """List of indicator rows."""

    indicators: list[IndicatorResponse]
    symbol: str
    timeframe: str
    count: int


class IndicatorLatestResponse(BaseModel):
    """Single latest indicator snapshot.

    ``indicator`` is None when the symbol+timeframe is valid but no indicator
    rows exist yet (e.g. the indicator calculator has not processed that
    timeframe) — callers should treat that as "no data yet", not an error.
    """

    indicator: Optional[IndicatorResponse] = None


class SupportResistanceResponse(BaseModel):
    """Support and resistance levels."""

    symbol: str
    timeframe: str
    timestamp: datetime
    support_levels: list[float]
    resistance_levels: list[float]


class FibonacciResponse(BaseModel):
    """Fibonacci retracement levels."""

    symbol: str
    timeframe: str
    timestamp: datetime
    fib_0: float
    fib_236: float
    fib_382: float
    fib_500: float
    fib_618: float
    fib_786: float
    fib_1: float
