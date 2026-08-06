"""BacktestRepository — persistence for BacktestRun and BacktestTrade."""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest import BacktestRun, BacktestTrade

logger = logging.getLogger(__name__)


class BacktestRepository:
    """Repository for BacktestRun and BacktestTrade persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Runs ──────────────────────────────────────────────────────────────────

    def add_run(self, run: BacktestRun) -> None:
        """Stage a BacktestRun for insertion."""
        self._session.add(run)

    async def get_run(self, run_id: str) -> BacktestRun | None:
        """Get a backtest run by ID."""
        stmt = select(BacktestRun).where(BacktestRun.id == run_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_runs_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[BacktestRun]:
        """Get backtest runs for a user, newest first."""
        stmt = (
            select(BacktestRun)
            .where(BacktestRun.user_id == user_id)
            .order_by(BacktestRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def delete_run(self, run_id: str) -> bool:
        """Delete a backtest run and its trades (cascade). Returns True if deleted."""
        stmt = delete(BacktestRun).where(BacktestRun.id == run_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0  # type: ignore[union-attr]

    # ── Trades ────────────────────────────────────────────────────────────────

    def add_trade(self, trade: BacktestTrade) -> None:
        """Stage a BacktestTrade for insertion."""
        self._session.add(trade)

    async def get_trades(self, run_id: str) -> Sequence[BacktestTrade]:
        """Get all trades for a backtest run, ordered by entry_time."""
        stmt = (
            select(BacktestTrade)
            .where(BacktestTrade.backtest_run_id == run_id)
            .order_by(BacktestTrade.entry_time.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def flush(self) -> None:
        """Flush pending changes to the database."""
        await self._session.flush()
