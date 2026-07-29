"""SMC Calculator Service — background service for auto-detecting SMC patterns.

Listens for candle_upsert events from the event hub and runs SMC detection.
Performs backfill on startup for all existing candles.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.database import async_session
from app.models.candle import Candle
from app.repositories.candle_repository import CandleRepository
from app.repositories.smc_repository import SMCRepository
from app.services.smc_detection import SMCDetectionService
from app.services.indicator_calculator import listen_event, unlisten_event
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES

logger = logging.getLogger(__name__)


class SMCCalculatorService:
    """Background service that detects SMC patterns on candle upsert events.

    Hooks into the event system to auto-detect when CandleSynchronizer
    produces new candles. Also performs a backfill on startup.
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._detection = SMCDetectionService()
        self._stats = {"detected": 0, "skipped": 0, "errors": 0}

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def start(self) -> None:
        if self._running:
            logger.warning("SMC calculator already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("SMC calculator started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SMC calculator stopped")

    async def _run(self) -> None:
        """Main loop: backfill on startup, then listen for events."""
        await self._backfill_existing()

        queue = listen_event("candle_upserted")
        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    if data is not None:
                        await self._handle_candle_event(data)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"SMC event handling error: {e}", exc_info=True)
                    self._stats["errors"] += 1
        finally:
            unlisten_event("candle_upserted", queue)

    async def _backfill_existing(self) -> None:
        """Detect SMC patterns for all existing candles."""
        logger.info("Starting SMC backfill for existing candles...")
        async with async_session() as session:
            candle_repo = CandleRepository(session)
            smc_repo = SMCRepository(session)

            for symbol in SUPPORTED_SYMBOLS:
                for tf in SUPPORTED_TIMEFRAMES:
                    try:
                        await self._backfill_symbol_tf(
                            session, candle_repo, smc_repo, symbol, tf
                        )
                    except Exception as e:
                        logger.error(f"SMC backfill error for {symbol}/{tf}: {e}")
                        self._stats["errors"] += 1

            await session.commit()
        logger.info(
            f"SMC backfill complete. "
            f"Detected: {self._stats['detected']}, "
            f"Errors: {self._stats['errors']}"
        )

    async def _backfill_symbol_tf(
        self,
        session: Any,
        candle_repo: CandleRepository,
        smc_repo: SMCRepository,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Backfill SMC detections for one symbol+timeframe pair.

        We fetch candles and run all SMC detection methods. Since each detection
        produces SMCStructure objects keyed by symbol+timeframe+timestamp+type+direction,
        the repository's upsert handles deduplication.
        """
        candles = await candle_repo.get_candles(symbol, timeframe, limit=300)
        if not candles:
            logger.debug(f"No candles to backfill SMC for {symbol}/{timeframe}")
            return

        structures = self._detection.detect_all(candles, symbol, timeframe)
        if not structures:
            return

        for struct in structures:
            try:
                # Check if already exists
                exists = await smc_repo.exists(
                    symbol, timeframe, struct.timestamp,
                    struct.structure_type, struct.direction,
                )
                if exists:
                    self._stats["skipped"] += 1
                    continue
                await smc_repo.upsert(struct)
                self._stats["detected"] += 1
            except Exception as e:
                logger.error(f"Error storing SMC structure: {e}")
                self._stats["errors"] += 1

    async def _handle_candle_event(self, data: Any) -> None:
        """Handle a candle_upserted event by running SMC detection."""
        symbol = None
        timeframe = None

        if isinstance(data, dict):
            symbol = data.get("symbol")
            timeframe = data.get("timeframe")
        elif hasattr(data, "symbol"):
            symbol = data.symbol
            timeframe = data.timeframe

        if not symbol or not timeframe:
            return

        async with async_session() as session:
            candle_repo = CandleRepository(session)
            smc_repo = SMCRepository(session)

            candles = await candle_repo.get_candles(symbol, timeframe, limit=300)
            if not candles:
                return

            structures = self._detection.detect_all(candles, symbol, timeframe)
            if not structures:
                return

            stored = 0
            for struct in structures:
                try:
                    exists = await smc_repo.exists(
                        symbol, timeframe, struct.timestamp,
                        struct.structure_type, struct.direction,
                    )
                    if exists:
                        continue
                    await smc_repo.upsert(struct)
                    stored += 1
                    self._stats["detected"] += 1
                except Exception as e:
                    logger.error(f"Error storing SMC structure on event: {e}")
                    self._stats["errors"] += 1

            if stored > 0:
                logger.debug(
                    f"SMC detected {stored} new structures for {symbol}/{timeframe}"
                )

            await session.commit()
