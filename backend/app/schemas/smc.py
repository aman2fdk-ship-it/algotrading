"""Schemas for SMC API responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SMCStructureResponse(BaseModel):
    """Single SMC pattern detection."""

    id: str
    symbol: str
    timeframe: str
    timestamp: datetime
    structure_type: str
    direction: str
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    price_mid: Optional[float] = None
    key_level: Optional[float] = None
    confidence: float
    details: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SMCListResponse(BaseModel):
    """List of SMC structures."""

    structures: list[SMCStructureResponse]
    symbol: str
    timeframe: str
    count: int


class SMCOrderBlockResponse(BaseModel):
    """Filtered order block data."""

    order_blocks: list[SMCStructureResponse]
    symbol: str
    timeframe: str
    count: int


class SMCLiquidityResponse(BaseModel):
    """Filtered liquidity sweep data."""

    liquidity_sweeps: list[SMCStructureResponse]
    symbol: str
    timeframe: str
    count: int


class SMCFVGResponse(BaseModel):
    """Filtered fair value gap data."""

    fair_value_gaps: list[SMCStructureResponse]
    symbol: str
    timeframe: str
    count: int


class SMCPremiumDiscountResponse(BaseModel):
    """Current premium/discount zone assessment."""

    symbol: str
    timeframe: str
    timestamp: datetime
    zone_type: str  # "premium", "discount", or "equilibrium"
    current_price: float
    swing_high: float
    swing_low: float
    position_pct: float  # 0.0 to 1.0 (0 = swing low, 1 = swing high)
