"""AIRecommendationRepository — persistence operations for AIRecommendation."""

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_recommendation import AIRecommendation

logger = logging.getLogger(__name__)


class AIRecommendationRepository:
    """Repository for AIRecommendation model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, recommendation: AIRecommendation) -> AIRecommendation:
        """Insert a new AI recommendation."""
        self._session.add(recommendation)
        await self._session.flush()
        return recommendation

    async def get_latest(self, symbol: str) -> AIRecommendation | None:
        """Get the most recent recommendation for a symbol."""
        stmt = (
            select(AIRecommendation)
            .where(AIRecommendation.symbol == symbol)
            .order_by(AIRecommendation.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 10) -> Sequence[AIRecommendation]:
        """Get the most recent recommendations across all symbols."""
        stmt = (
            select(AIRecommendation)
            .order_by(AIRecommendation.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_symbol(
        self, symbol: str, limit: int = 20
    ) -> Sequence[AIRecommendation]:
        """Get recent recommendations for a specific symbol."""
        stmt = (
            select(AIRecommendation)
            .where(AIRecommendation.symbol == symbol)
            .order_by(AIRecommendation.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
