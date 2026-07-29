"""RiskSettingsService — DB-backed service for loss limits and risk status."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from app.models.risk_settings import RiskSettings
from app.repositories.risk_repository import RiskSettingsRepository

logger = logging.getLogger(__name__)


@dataclass
class RiskLimitStatus:
    """Result of a loss limit check."""
    trading_allowed: bool
    daily_loss: float
    weekly_loss: float
    max_daily_loss: float | None
    max_weekly_loss: float | None
    max_daily_loss_pct: float | None
    max_weekly_loss_pct: float | None
    daily_used_pct: float | None  # % of daily limit used
    weekly_used_pct: float | None  # % of weekly limit used
    reason: str | None  # None if allowed, else the blocking reason


@dataclass
class UpdateSettingsRequest:
    """Data needed to update risk settings."""
    max_daily_loss: float | None = None
    max_weekly_loss: float | None = None
    max_daily_loss_pct: float | None = None
    max_weekly_loss_pct: float | None = None


class RiskSettingsService:
    """Service for managing user risk settings and checking loss limits."""

    def __init__(self, repository: RiskSettingsRepository) -> None:
        self._repo = repository

    async def get_settings(self, user_id: str) -> RiskSettings:
        """Get or create risk settings for a user."""
        return await self._repo.get_or_create(user_id)

    async def update_settings(
        self, user_id: str, updates: UpdateSettingsRequest
    ) -> RiskSettings:
        """Update risk settings for a user. Only non-None fields are updated."""
        settings = await self._repo.get_or_create(user_id)

        if updates.max_daily_loss is not None:
            settings.max_daily_loss = updates.max_daily_loss
        if updates.max_weekly_loss is not None:
            settings.max_weekly_loss = updates.max_weekly_loss
        if updates.max_daily_loss_pct is not None:
            settings.max_daily_loss_pct = updates.max_daily_loss_pct
        if updates.max_weekly_loss_pct is not None:
            settings.max_weekly_loss_pct = updates.max_weekly_loss_pct

        settings.updated_at = datetime.now(timezone.utc)
        return await self._repo.update(settings)

    async def check_limits(self, user_id: str) -> RiskLimitStatus:
        """Check whether the user has hit any loss limits.

        Returns:
            RiskLimitStatus indicating whether trading is allowed and usage percentages.
        """
        settings = await self._repo.get_or_create(user_id)

        # Sanity-check resets
        now = datetime.now(timezone.utc)
        daily_reset = await self._maybe_reset_daily(settings, now)
        weekly_reset = await self._maybe_reset_weekly(settings, now)

        if daily_reset or weekly_reset:
            settings = await self._repo.get_by_user_id(user_id)

        daily_loss = settings.current_daily_loss
        weekly_loss = settings.current_weekly_loss

        reason: str | None = None

        # Check absolute daily loss
        if settings.max_daily_loss is not None and daily_loss >= settings.max_daily_loss:
            reason = f"Daily loss limit reached: ${daily_loss:.2f} >= ${settings.max_daily_loss:.2f}"

        # Check absolute weekly loss
        if settings.max_weekly_loss is not None and weekly_loss >= settings.max_weekly_loss:
            reason = f"Weekly loss limit reached: ${weekly_loss:.2f} >= ${settings.max_weekly_loss:.2f}"

        # Calculate percentages
        daily_used_pct: float | None = None
        weekly_used_pct: float | None = None

        if settings.max_daily_loss is not None and settings.max_daily_loss > 0:
            daily_used_pct = round((daily_loss / settings.max_daily_loss) * 100.0, 2)
        elif settings.max_daily_loss_pct is not None:
            daily_used_pct = round(daily_loss, 2)  # stored as percentage of balance...

        if settings.max_weekly_loss is not None and settings.max_weekly_loss > 0:
            weekly_used_pct = round((weekly_loss / settings.max_weekly_loss) * 100.0, 2)
        elif settings.max_weekly_loss_pct is not None:
            weekly_used_pct = round(weekly_loss, 2)

        # Percentage-based limits are checked at point of trade, not here
        # (since we need account_balance to calculate)

        trading_allowed = reason is None

        return RiskLimitStatus(
            trading_allowed=trading_allowed,
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            max_daily_loss=settings.max_daily_loss,
            max_weekly_loss=settings.max_weekly_loss,
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_weekly_loss_pct=settings.max_weekly_loss_pct,
            daily_used_pct=daily_used_pct,
            weekly_used_pct=weekly_used_pct,
            reason=reason,
        )

    async def check_limits_with_balance(
        self, user_id: str, account_balance: float
    ) -> RiskLimitStatus:
        """Check loss limits including percentage-based ones.

        Args:
            user_id: The user to check.
            account_balance: Current account balance for %-based limit calculation.
        """
        settings = await self._repo.get_or_create(user_id)

        now = datetime.now(timezone.utc)
        daily_reset = await self._maybe_reset_daily(settings, now)
        weekly_reset = await self._maybe_reset_weekly(settings, now)

        if daily_reset or weekly_reset:
            settings = await self._repo.get_by_user_id(user_id)

        daily_loss = settings.current_daily_loss
        weekly_loss = settings.current_weekly_loss

        reason: str | None = None

        # Absolute limits
        if settings.max_daily_loss is not None and daily_loss >= settings.max_daily_loss:
            reason = f"Daily loss limit reached: ${daily_loss:.2f} >= ${settings.max_daily_loss:.2f}"

        if settings.max_weekly_loss is not None and weekly_loss >= settings.max_weekly_loss:
            reason = f"Weekly loss limit reached: ${weekly_loss:.2f} >= ${settings.max_weekly_loss:.2f}"

        # Percentage-based limits
        if settings.max_daily_loss_pct is not None and account_balance > 0:
            max_daily_abs = account_balance * (settings.max_daily_loss_pct / 100.0)
            if daily_loss >= max_daily_abs:
                reason = (
                    f"Daily loss limit reached: ${daily_loss:.2f} >= "
                    f"{settings.max_daily_loss_pct}% of ${account_balance:.2f} = ${max_daily_abs:.2f}"
                )

        if settings.max_weekly_loss_pct is not None and account_balance > 0:
            max_weekly_abs = account_balance * (settings.max_weekly_loss_pct / 100.0)
            if weekly_loss >= max_weekly_abs:
                reason = (
                    f"Weekly loss limit reached: ${weekly_loss:.2f} >= "
                    f"{settings.max_weekly_loss_pct}% of ${account_balance:.2f} = ${max_weekly_abs:.2f}"
                )

        # Calculate percentages
        daily_used_pct: float | None = None
        weekly_used_pct: float | None = None

        if settings.max_daily_loss is not None and settings.max_daily_loss > 0:
            daily_used_pct = round((daily_loss / settings.max_daily_loss) * 100.0, 2)
        elif settings.max_daily_loss_pct is not None and account_balance > 0:
            max_daily_abs = account_balance * (settings.max_daily_loss_pct / 100.0)
            daily_used_pct = round((daily_loss / max_daily_abs) * 100.0, 2) if max_daily_abs > 0 else 0.0

        if settings.max_weekly_loss is not None and settings.max_weekly_loss > 0:
            weekly_used_pct = round((weekly_loss / settings.max_weekly_loss) * 100.0, 2)
        elif settings.max_weekly_loss_pct is not None and account_balance > 0:
            max_weekly_abs = account_balance * (settings.max_weekly_loss_pct / 100.0)
            weekly_used_pct = round((weekly_loss / max_weekly_abs) * 100.0, 2) if max_weekly_abs > 0 else 0.0

        trading_allowed = reason is None

        return RiskLimitStatus(
            trading_allowed=trading_allowed,
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            max_daily_loss=settings.max_daily_loss,
            max_weekly_loss=settings.max_weekly_loss,
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_weekly_loss_pct=settings.max_weekly_loss_pct,
            daily_used_pct=daily_used_pct,
            weekly_used_pct=weekly_used_pct,
            reason=reason,
        )

    async def record_loss(self, user_id: str, loss_amount: float) -> RiskSettings:
        """Record a loss, incrementing the daily and weekly running totals.

        Negative loss_amounts (profits) are ignored (do not reduce the counter).
        """
        settings = await self._repo.get_or_create(user_id)
        now = datetime.now(timezone.utc)

        # Auto-reset if needed
        await self._maybe_reset_daily(settings, now)
        await self._maybe_reset_weekly(settings, now)

        if loss_amount > 0:
            settings.current_daily_loss += loss_amount
            settings.current_weekly_loss += loss_amount
            settings.updated_at = now

        return await self._repo.update(settings)

    async def reset_daily(self, user_id: str) -> RiskSettings:
        """Reset the daily loss counter."""
        settings = await self._repo.get_or_create(user_id)
        settings.current_daily_loss = 0.0
        settings.last_daily_reset = datetime.now(timezone.utc)
        settings.updated_at = datetime.now(timezone.utc)
        return await self._repo.update(settings)

    async def reset_weekly(self, user_id: str) -> RiskSettings:
        """Reset the weekly loss counter."""
        settings = await self._repo.get_or_create(user_id)
        settings.current_weekly_loss = 0.0
        settings.last_weekly_reset = datetime.now(timezone.utc)
        settings.updated_at = datetime.now(timezone.utc)
        return await self._repo.update(settings)

    # ── Internal helpers ────────────────────────────────────────────────────────

    async def _maybe_reset_daily(
        self, settings: RiskSettings, now: datetime
    ) -> bool:
        """Reset daily counter if the last reset was a different calendar day."""
        last = settings.last_daily_reset
        if last is None or last.date() < now.date():
            settings.current_daily_loss = 0.0
            settings.last_daily_reset = now
            settings.updated_at = now
            await self._repo.update(settings)
            return True
        return False

    async def _maybe_reset_weekly(
        self, settings: RiskSettings, now: datetime
    ) -> bool:
        """Reset weekly counter if the last reset was a different ISO week."""
        last = settings.last_weekly_reset
        if last is None or (
            last.isocalendar()[0] != now.isocalendar()[0]
            or last.isocalendar()[1] != now.isocalendar()[1]
        ):
            settings.current_weekly_loss = 0.0
            settings.last_weekly_reset = now
            settings.updated_at = now
            await self._repo.update(settings)
            return True
        return False
