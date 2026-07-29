from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Tick(Base):
    """Individual tick (bid/ask) data for a symbol."""

    __tablename__ = "ticks"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_tick_symbol_ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bid: Mapped[float] = mapped_column(Float, nullable=False)
    ask: Mapped[float] = mapped_column(Float, nullable=False)
    spread: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Tick {self.symbol} {self.timestamp} B:{self.bid} A:{self.ask}>"
