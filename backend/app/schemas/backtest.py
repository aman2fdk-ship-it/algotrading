"""Pydantic schemas for Backtest API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────────────────


class BacktestRunRequest(BaseModel):
    """Request body to run a new backtest."""

    symbol: str = Field(..., description="Trading symbol code, e.g. EURUSD")
    timeframe: str = Field(..., description="Timeframe, e.g. H1")
    start_date: datetime = Field(..., description="Start of historical data range")
    end_date: datetime = Field(..., description="End of historical data range")
    initial_balance: float = Field(..., gt=0, description="Starting account balance")
    risk_percentage: float = Field(
        ..., ge=0, le=100, description="% risk per trade (e.g. 1.0 = 1%)"
    )


# ── Trade Response ───────────────────────────────────────────────────────────────


class BacktestTradeResponse(BaseModel):
    """Single trade in a backtest run."""

    id: str
    symbol: str
    timeframe: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Monthly Performance ──────────────────────────────────────────────────────────


class MonthlyPerformanceItem(BaseModel):
    """Performance for a single month."""

    month: str  # "YYYY-MM"
    return_pct: float
    trades: int
    win_rate: float  # 0–100


# ── Equity Curve Point ───────────────────────────────────────────────────────────


class EquityCurvePoint(BaseModel):
    """A point on the equity curve."""

    timestamp: str  # ISO 8601
    balance: float


# ── Full Backtest Result Response ────────────────────────────────────────────────


class BacktestResultResponse(BaseModel):
    """Full backtest result with all metrics and trades."""

    id: str
    user_id: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    risk_percentage: float
    final_balance: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: Optional[float] = None
    max_drawdown: float
    max_drawdown_amount: float
    expectancy: float
    sharpe_ratio: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    largest_win: Optional[float] = None
    largest_loss: Optional[float] = None
    avg_hold_time: Optional[float] = None  # seconds
    equity_curve: list[EquityCurvePoint]
    trades: list[BacktestTradeResponse]
    monthly_performance: list[MonthlyPerformanceItem]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Summary (list item) ─────────────────────────────────────────────────────────


class BacktestRunSummary(BaseModel):
    """Summary of a backtest run (no trades, no equity curve details)."""

    id: str
    user_id: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    risk_percentage: float
    final_balance: float
    total_trades: int
    win_rate: float
    profit_factor: Optional[float] = None
    max_drawdown: float
    expectancy: float
    sharpe_ratio: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BacktestRunListResponse(BaseModel):
    """List of backtest summaries."""

    runs: list[BacktestRunSummary]
    count: int


# ── Delete Response ──────────────────────────────────────────────────────────────


class BacktestDeleteResponse(BaseModel):
    """Response after deleting a backtest run."""

    message: str
