"""Pydantic schemas for Risk Management API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RiskCalculateRequest(BaseModel):
    """Request body for position size + margin calculation."""
    account_balance: float = Field(..., gt=0, description="Total account equity")
    risk_percentage: float = Field(
        ..., ge=0, le=100, description="% of account to risk (e.g., 1.0 = 1%)"
    )
    entry_price: float = Field(..., gt=0, description="Planned entry price")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")
    symbol: str = Field(..., description="Trading symbol code, e.g. EURUSD")
    leverage: float = Field(..., gt=0, description="Leverage ratio, e.g. 100")


class RiskCalculateResponse(BaseModel):
    """Response for full risk calculation."""
    symbol: str
    account_balance: float
    risk_percentage: float
    entry_price: float
    stop_loss: float
    leverage: float
    position_size: float
    risk_amount: float
    stop_loss_pips: float
    lot_size: float
    mini_lots: float
    micro_lots: float
    required_margin: float
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    potential_profit_tp1: Optional[float] = None
    potential_profit_tp2: Optional[float] = None
    risk_reward_ratio_tp1: Optional[float] = None
    risk_reward_ratio_tp2: Optional[float] = None
    pip_size: float
    pip_value: float


class PipValueItem(BaseModel):
    """Single symbol pip value info."""
    symbol: str
    pip_size: float
    pip_value_per_lot: float


class PipValuesResponse(BaseModel):
    """List of all symbol pip values."""
    symbols: list[PipValueItem]
    count: int


class RiskLimitsResponse(BaseModel):
    """Current user loss limits and running counters."""
    user_id: str
    max_daily_loss: Optional[float] = None
    max_weekly_loss: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_weekly_loss_pct: Optional[float] = None
    current_daily_loss: float
    current_weekly_loss: float
    last_daily_reset: datetime
    last_weekly_reset: datetime
    created_at: datetime
    updated_at: datetime


class RiskLimitsUpdateRequest(BaseModel):
    """Request to update loss limits. Only provided fields are changed."""
    max_daily_loss: Optional[float] = Field(None, ge=0, description="Max daily loss in USD")
    max_weekly_loss: Optional[float] = Field(None, ge=0, description="Max weekly loss in USD")
    max_daily_loss_pct: Optional[float] = Field(None, ge=0, le=100, description="Max daily loss as % of balance")
    max_weekly_loss_pct: Optional[float] = Field(None, ge=0, le=100, description="Max weekly loss as % of balance")


class RiskStatusResponse(BaseModel):
    """Response for trading status check."""
    trading_allowed: bool
    daily_loss: float
    weekly_loss: float
    max_daily_loss: Optional[float] = None
    max_weekly_loss: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_weekly_loss_pct: Optional[float] = None
    daily_used_pct: Optional[float] = None
    weekly_used_pct: Optional[float] = None
    reason: Optional[str] = None


class RiskResetResponse(BaseModel):
    """Response after resetting loss counters."""
    message: str
    current_daily_loss: float
    current_weekly_loss: float
