"""RiskSettings model — per-user risk management configuration."""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RiskSettings(Base):
    """Per-user risk management settings and running loss counters."""

    __tablename__ = "risk_settings"

    user_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, nullable=False
    )
    max_daily_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    max_weekly_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    max_daily_loss_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    max_weekly_loss_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    current_daily_loss: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    current_weekly_loss: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    last_daily_reset: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_weekly_reset: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RiskSettings user={self.user_id} daily={self.current_daily_loss:.2f}>"
