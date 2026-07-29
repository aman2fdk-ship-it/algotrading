"""Market Status Monitor — tracks which symbols are currently tradeable.

Polls MT5 to check symbol availability and updates market status in the database.
Runs independently from the session detector.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.repositories.market_status_repository import MarketStatusRepository
from app.services.mt5_client import MT5ClientProtocol, SUPPORTED_SYMBOLS

logger = logging.getLogger(__name__)

MONITOR_INTERVAL = 30.0  # Check every 30 seconds


class MarketStatusMonitor:
    """Background service that monitors symbol tradeability from MT5."""

    def __init__(self, mt5_client: MT5ClientProtocol) -> None:
        self._client = mt5_client
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            logger.warning("Market status monitor already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Market status monitor started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Market status monitor stopped")

    async def _run(self) -> None:
        while self._running:
            try:
                if await self._client.is_connected():
                    await self._check_symbols()
                await asyncio.sleep(MONITOR_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Market status monitor error: {e}", exc_info=True)
                await asyncio.sleep(10.0)

    async def _check_symbols(self) -> None:
        """Check which symbols are available on the connected MT5 terminal."""
        try:
            available = await self._client.get_symbols()
        except Exception as e:
            logger.warning(f"Could not fetch symbol list from MT5: {e}")
            return

        async with async_session() as session:
            repo = MarketStatusRepository(session)

            for symbol in SUPPORTED_SYMBOLS:
                is_available = symbol in available if available else True  # Default to True if can't check
                current = await repo.get_by_symbol(symbol)

                if current is None:
                    await repo.upsert_status(symbol, is_available, "unknown")
                elif not is_available and current.is_open:
                    logger.warning(f"Symbol {symbol} is no longer available on MT5")
                    await repo.upsert_status(symbol, False, current.session)

            await session.commit()
