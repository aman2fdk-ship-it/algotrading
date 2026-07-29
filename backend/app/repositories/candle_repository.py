import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle

logger = logging.getLogger(__name__)


class CandleRepository:
    """Repository for Candle (OHLCV) model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        before: datetime | None = None,
    ) -> Sequence[Candle]:
        stmt = select(Candle).where(
            and_(Candle.symbol == symbol, Candle.timeframe == timeframe)
        )
        if before:
            stmt = stmt.where(Candle.timestamp < before)
        stmt = stmt.order_by(Candle.timestamp.desc()).limit(limit)
        result = await self._session.execute(stmt)
        candles = result.scalars().all()
        return list(reversed(candles))  # chronological order

    async def upsert_candle(self, candle: Candle) -> Candle:
        """Insert or update a candle using find-then-upsert (DB agnostic)."""
        existing = await self._session.execute(
            select(Candle).where(
                and_(
                    Candle.symbol == candle.symbol,
                    Candle.timeframe == candle.timeframe,
                    Candle.timestamp == candle.timestamp,
                )
            )
        )
        existing_candle = existing.scalar_one_or_none()

        if existing_candle:
            existing_candle.open = candle.open
            existing_candle.high = candle.high
            existing_candle.low = candle.low
            existing_candle.close = candle.close
            existing_candle.tick_volume = candle.tick_volume
            existing_candle.real_volume = candle.real_volume
            existing_candle.spread = candle.spread
            await self._session.flush()
            return existing_candle
        else:
            self._session.add(candle)
            await self._session.flush()
            return candle

    async def upsert_candles(self, candles: list[Candle]) -> int:
        """Bulk upsert candles. Returns number upserted."""
        count = 0
        for candle in candles:
            await self.upsert_candle(candle)
            count += 1
        return count

    async def get_latest_candle(
        self, symbol: str, timeframe: str
    ) -> Candle | None:
        stmt = (
            select(Candle)
            .where(and_(Candle.symbol == symbol, Candle.timeframe == timeframe))
            .order_by(Candle.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
