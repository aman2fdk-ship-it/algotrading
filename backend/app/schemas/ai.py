"""Pydantic schemas for AI Decision Engine API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request body for single-symbol AI analysis."""
    symbol: str = Field(..., description="Trading symbol code, e.g. EURUSD")


class AnalyzeBatchRequest(BaseModel):
    """Request body for batch AI analysis."""
    symbols: list[str] = Field(
        ..., min_length=1, max_length=10, description="List of symbol codes"
    )


class TimeframeScoreDetail(BaseModel):
    """Per-timeframe score breakdown for debugging."""
    timeframe: str
    score: float
    weight: float
    category_scores: dict[str, float] = Field(default_factory=dict)


class DecisionResult(BaseModel):
    """Complete AI decision output."""
    symbol: str
    decision: str  # BUY, SELL, WAIT
    confidence: float  # 0–100
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    trend: str  # Bullish, Bearish, Ranging
    market_bias: str  # Strong Buy, Buy, Neutral, Sell, Strong Sell
    risk_level: str  # Low, Medium, High
    reasoning: str
    timeframe_scores: dict[str, float] = Field(default_factory=dict)
    timeframe_details: list[TimeframeScoreDetail] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class RecommendationResponse(BaseModel):
    """Persisted recommendation."""
    id: str
    symbol: str
    decision: str
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    trend: str
    market_bias: str
    risk_level: str
    reasoning: str
    timeframe_scores: dict[str, float] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationListResponse(BaseModel):
    """List of recent recommendations."""
    recommendations: list[RecommendationResponse]
    count: int
