from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MarketStatus(Base):
    """Current market session status for a symbol."""

    __tablename__ = "market_status"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session: Mapped[str] = mapped_column(
        String(20), nullable=False, default="closed"
    )  # Asian, London, NY, closed
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MarketStatus {self.symbol} open={self.is_open} session={self.session}>"
