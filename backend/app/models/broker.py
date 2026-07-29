from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BrokerInfo(Base):
    """Broker information from the connected MT5 terminal."""

    __tablename__ = "broker_info"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Unknown")
    server: Mapped[str] = mapped_column(String(100), nullable=False, default="Unknown")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    regulation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<BrokerInfo {self.name} ({self.server})>"
