"""RiskSettingsRepository — persistence operations for RiskSettings."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_settings import RiskSettings

logger = logging.getLogger(__name__)


class RiskSettingsRepository:
    """Repository for RiskSettings model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: str) -> RiskSettings | None:
        """Get risk settings for a user, or None."""
        stmt = select(RiskSettings).where(RiskSettings.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, settings: RiskSettings) -> RiskSettings:
        """Create a new risk settings row."""
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def get_or_create(self, user_id: str) -> RiskSettings:
        """Get or create risk settings for a user."""
        settings = await self.get_by_user_id(user_id)
        if settings is None:
            now = datetime.now(timezone.utc)
            settings = RiskSettings(
                user_id=user_id,
                current_daily_loss=0.0,
                current_weekly_loss=0.0,
                last_daily_reset=now,
                last_weekly_reset=now,
            )
            self._session.add(settings)
            await self._session.flush()
        return settings

    async def update(self, settings: RiskSettings) -> RiskSettings:
        """Update existing risk settings (merges into the session)."""
        await self._session.flush()
        return settings
