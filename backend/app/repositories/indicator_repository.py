"""IndicatorRepository — persistence operations for TechnicalIndicator."""

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.technical_indicator import TechnicalIndicator

logger = logging.getLogger(__name__)


class IndicatorRepository:
    """Repository for TechnicalIndicator model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, indicator: TechnicalIndicator) -> TechnicalIndicator:
        """Insert or update an indicator row by unique constraint (symbol+timeframe+timestamp)."""
        existing = await self._session.execute(
            select(TechnicalIndicator).where(
                and_(
                    TechnicalIndicator.symbol == indicator.symbol,
                    TechnicalIndicator.timeframe == indicator.timeframe,
                    TechnicalIndicator.timestamp == indicator.timestamp,
                )
            )
        )
        existing_indicator = existing.scalar_one_or_none()

        if existing_indicator:
            # Update all indicator fields
            existing_indicator.ema_20 = indicator.ema_20
            existing_indicator.ema_50 = indicator.ema_50
            existing_indicator.ema_200 = indicator.ema_200
            existing_indicator.supertrend_direction = indicator.supertrend_direction
            existing_indicator.supertrend_value = indicator.supertrend_value
            existing_indicator.adx = indicator.adx
            existing_indicator.rsi = indicator.rsi
            existing_indicator.macd_line = indicator.macd_line
            existing_indicator.macd_signal = indicator.macd_signal
            existing_indicator.macd_histogram = indicator.macd_histogram
            existing_indicator.stoch_k = indicator.stoch_k
            existing_indicator.stoch_d = indicator.stoch_d
            existing_indicator.atr = indicator.atr
            existing_indicator.bb_upper = indicator.bb_upper
            existing_indicator.bb_middle = indicator.bb_middle
            existing_indicator.bb_lower = indicator.bb_lower
            existing_indicator.vwap = indicator.vwap
            existing_indicator.support_levels = indicator.support_levels
            existing_indicator.resistance_levels = indicator.resistance_levels
            existing_indicator.swing_high = indicator.swing_high
            existing_indicator.swing_low = indicator.swing_low
            existing_indicator.fib_236 = indicator.fib_236
            existing_indicator.fib_382 = indicator.fib_382
            existing_indicator.fib_500 = indicator.fib_500
            existing_indicator.fib_618 = indicator.fib_618
            existing_indicator.fib_786 = indicator.fib_786
            await self._session.flush()
            return existing_indicator
        else:
            self._session.add(indicator)
            await self._session.flush()
            return indicator

    async def exists(self, symbol: str, timeframe: str, timestamp: datetime) -> bool:
        """Check if an indicator row already exists."""
        result = await self._session.execute(
            select(TechnicalIndicator).where(
                and_(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == timeframe,
                    TechnicalIndicator.timestamp == timestamp,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_symbol_timeframe(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> Sequence[TechnicalIndicator]:
        """Get the latest N indicator rows for a symbol+timeframe."""
        stmt = (
            select(TechnicalIndicator)
            .where(
                and_(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == timeframe,
                )
            )
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        indicators = result.scalars().all()
        return list(reversed(indicators))  # chronological order

    async def get_latest(
        self, symbol: str, timeframe: str
    ) -> TechnicalIndicator | None:
        """Get the single latest indicator row."""
        stmt = (
            select(TechnicalIndicator)
            .where(
                and_(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == timeframe,
                )
            )
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_range(
        self,
        symbol: str,
        timeframe: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> Sequence[TechnicalIndicator]:
        """Get indicator rows within a date range."""
        stmt = (
            select(TechnicalIndicator)
            .where(
                and_(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == timeframe,
                    TechnicalIndicator.timestamp >= from_ts,
                    TechnicalIndicator.timestamp <= to_ts,
                )
            )
            .order_by(TechnicalIndicator.timestamp.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
