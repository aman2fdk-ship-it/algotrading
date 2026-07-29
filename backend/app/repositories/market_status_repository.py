import logging
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_status import MarketStatus

logger = logging.getLogger(__name__)


class MarketStatusRepository:
    """Repository for MarketStatus model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all(self) -> Sequence[MarketStatus]:
        result = await self._session.execute(
            select(MarketStatus).order_by(MarketStatus.symbol)
        )
        return result.scalars().all()

    async def get_by_symbol(self, symbol: str) -> MarketStatus | None:
        result = await self._session.execute(
            select(MarketStatus).where(MarketStatus.symbol == symbol)
        )
        return result.scalar_one_or_none()

    async def upsert_status(
        self, symbol: str, is_open: bool, session: str
    ) -> MarketStatus:
        """Insert or update market status for a symbol."""
        existing = await self.get_by_symbol(symbol)
        if existing:
            existing.is_open = is_open
            existing.session = session
            existing.last_updated = datetime.now(timezone.utc)
            await self._session.flush()
            return existing
        else:
            ms = MarketStatus(
                symbol=symbol,
                is_open=is_open,
                session=session,
                last_updated=datetime.now(timezone.utc),
            )
            self._session.add(ms)
            await self._session.flush()
            return ms

    async def bulk_upsert(self, statuses: list[dict]) -> int:
        """Bulk upsert market statuses. Returns count updated."""
        count = 0
        for s in statuses:
            await self.upsert_status(
                symbol=s["symbol"],
                is_open=s["is_open"],
                session=s["session"],
            )
            count += 1
        return count
