"""SMC Structure model — institutional SMC/ICT pattern detections."""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, UniqueConstraint, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SMCStructure(Base):
    """Stores all Smart Money Concepts (SMC) pattern detections."""

    __tablename__ = "smc_structures"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp", "structure_type", "direction",
            name="uq_smc_symbol_tf_ts_type_dir",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    structure_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # "bos", "choch", "order_block", "fvg", "liquidity_sweep", "equal_highs", "equal_lows", "premium_discount"
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "bullish" or "bearish"
    price_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_mid: Mapped[float | None] = mapped_column(Float, nullable=True)
    key_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SMCStructure {self.structure_type} {self.direction} "
            f"{self.symbol}/{self.timeframe} @{self.timestamp}>"
        )
