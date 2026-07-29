"""Technical Indicator model — calculated indicator values per candle."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TechnicalIndicator(Base):
    """Stores all calculated technical indicators for a symbol+timeframe+timestamp."""

    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_indicator_symbol_tf_ts"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # ── Trend Indicators ───────────────────────────────────────────────────────
    ema_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema_200: Mapped[float | None] = mapped_column(Float, nullable=True)
    supertrend_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supertrend_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    adx: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Momentum Indicators ────────────────────────────────────────────────────
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_histogram: Mapped[float | None] = mapped_column(Float, nullable=True)
    stoch_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    stoch_d: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Volatility Indicators ──────────────────────────────────────────────────
    atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_middle: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_lower: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Volume Indicators ──────────────────────────────────────────────────────
    vwap: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Price Action ───────────────────────────────────────────────────────────
    support_levels: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    resistance_levels: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    swing_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    swing_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    fib_236: Mapped[float | None] = mapped_column(Float, nullable=True)
    fib_382: Mapped[float | None] = mapped_column(Float, nullable=True)
    fib_500: Mapped[float | None] = mapped_column(Float, nullable=True)
    fib_618: Mapped[float | None] = mapped_column(Float, nullable=True)
    fib_786: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TechnicalIndicator {self.symbol} {self.timeframe} {self.timestamp}>"
