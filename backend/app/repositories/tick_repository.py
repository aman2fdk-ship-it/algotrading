import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tick import Tick

logger = logging.getLogger(__name__)


class TickRepository:
    """Repository for Tick model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_ticks(
        self,
        symbol: str,
        limit: int = 1000,
        before: datetime | None = None,
    ) -> Sequence[Tick]:
        stmt = select(Tick).where(Tick.symbol == symbol)
        if before:
            stmt = stmt.where(Tick.timestamp < before)
        stmt = stmt.order_by(Tick.timestamp.desc()).limit(limit)
        result = await self._session.execute(stmt)
        ticks = result.scalars().all()
        return list(reversed(ticks))

    async def get_latest_tick(self, symbol: str) -> Tick | None:
        stmt = (
            select(Tick)
            .where(Tick.symbol == symbol)
            .order_by(Tick.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_tick(self, tick: Tick) -> Tick:
        """Insert a tick; skip if duplicate timestamp for this symbol."""
        # Check for existing tick with same symbol+timestamp
        existing = await self._session.execute(
            select(Tick).where(
                Tick.symbol == tick.symbol,
                Tick.timestamp == tick.timestamp,
            )
        )
        if existing.scalar_one_or_none() is None:
            self._session.add(tick)
            await self._session.flush()
        return tick

    async def upsert_ticks(self, ticks: list[Tick]) -> tuple[int, int]:
        """Bulk upsert ticks. Returns (inserted, skipped)."""
        inserted = 0
        skipped = 0
        for tick in ticks:
            existing = await self._session.execute(
                select(Tick).where(
                    Tick.symbol == tick.symbol,
                    Tick.timestamp == tick.timestamp,
                )
            )
            if existing.scalar_one_or_none() is None:
                self._session.add(tick)
                inserted += 1
            else:
                skipped += 1
        await self._session.flush()
        return inserted, skipped
