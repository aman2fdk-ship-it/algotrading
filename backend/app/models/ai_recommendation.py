"""AI Recommendation model — stores multi-factor decision results."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AIRecommendation(Base):
    """Persisted AI decision for a symbol at a point in time."""

    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL, WAIT
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0–100
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend: Mapped[str] = mapped_column(String(20), nullable=False)  # Bullish, Bearish, Ranging
    market_bias: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # Low, Medium, High
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe_scores: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AIRecommendation {self.symbol} {self.decision} conf={self.confidence:.1f}>"
