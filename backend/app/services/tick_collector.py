"""Live Tick Collector — polls MT5 for current ticks and writes them to the database."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.tick import Tick
from app.repositories.tick_repository import TickRepository
from app.services.mt5_client import MT5ClientProtocol, SUPPORTED_SYMBOLS, TickData
from app.services.observability import metrics
from app.config import settings

logger = logging.getLogger(__name__)

TICK_WRITE_INTERVAL = 0.5  # Poll every 500ms
BATCH_SIZE = 50  # Write ticks in batches


class LiveTickCollector:
    """Background service that collects live ticks from MT5 and persists them."""

    def __init__(self, mt5_client: MT5ClientProtocol) -> None:
        self._client = mt5_client
        self._running = False
        self._task: asyncio.Task | None = None
        self._stats = {"received": 0, "written": 0, "skipped": 0, "errors": 0}

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def start(self) -> None:
        if self._running:
            logger.warning("Tick collector already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Live tick collector started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Live tick collector stopped")

    async def _run(self) -> None:
        """Main collection loop."""
        tick_batch: list[TickData] = []

        while self._running:
            try:
                if not await self._client.is_connected():
                    logger.debug("MT5 not connected, skipping tick collection")
                    await asyncio.sleep(1.0)
                    continue

                for symbol in SUPPORTED_SYMBOLS:
                    try:
                        tick = await self._get_tick(symbol)
                        if tick:
                            tick_batch.append(tick)
                            self._stats["received"] += 1
                            # Heartbeat for the observability feed-status panel.
                            metrics.touch_feed()
                    except Exception as e:
                        logger.error(f"Error fetching tick for {symbol}: {e}")
                        self._stats["errors"] += 1

                # Flush batch if full
                if len(tick_batch) >= BATCH_SIZE:
                    await self._persist_ticks(tick_batch)
                    tick_batch = []

                await asyncio.sleep(TICK_WRITE_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick collector error: {e}", exc_info=True)
                self._stats["errors"] += 1
                await asyncio.sleep(1.0)

        # Flush remaining ticks on stop
        if tick_batch:
            await self._persist_ticks(tick_batch)

    async def _get_tick(self, symbol: str) -> TickData | None:
        """Get current tick for a symbol from the MT5 client."""
        client = self._client
        # Try the get_current_tick method if available
        get_current = getattr(client, "get_current_tick", None)
        if callable(get_current):
            return await get_current(symbol)
        return None

    async def _persist_ticks(self, ticks: list[TickData]) -> None:
        """Write a batch of ticks to the database."""
        if not ticks:
            return
        try:
            async with async_session() as session:
                repo = TickRepository(session)
                for td in ticks:
                    tick = Tick(
                        symbol=td.symbol,
                        timestamp=td.timestamp,
                        bid=td.bid,
                        ask=td.ask,
                        spread=td.spread,
                        volume=td.volume,
                    )
                    try:
                        await repo.upsert_tick(tick)
                        self._stats["written"] += 1
                    except Exception:
                        self._stats["skipped"] += 1
                await session.commit()
            logger.debug(f"Persisted {len(ticks)} ticks (total written: {self._stats['written']})")
        except Exception as e:
            logger.error(f"Failed to persist ticks: {e}")
            self._stats["errors"] += len(ticks)
