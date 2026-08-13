"""Indicator Calculator Service — background service for auto-calculating indicators.

Listens for candle upsert events from the CandleSynchronizer and calculates
all technical indicators. Also performs backfill on startup.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import async_session
from app.models.candle import Candle
from app.repositories.candle_repository import CandleRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.services.technical_analysis import TechnicalAnalysisService
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES

logger = logging.getLogger(__name__)

# Event hub for candle upserts — other services can publish/listen
# Key: "candle_upserted" -> asyncio.Event
_event_hub: dict[str, list[asyncio.Queue]] = {}


def emit_event(event_name: str, data: Any = None) -> None:
    """Emit an event to all listeners.

    Called by CandleSynchronizer when it upserts candles.
    """
    queues = _event_hub.get(event_name, [])
    for q in queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass  # Drop if listener is too slow


def listen_event(event_name: str) -> asyncio.Queue:
    """Register a listener for an event. Returns an async Queue to read from."""
    if event_name not in _event_hub:
        _event_hub[event_name] = []
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _event_hub[event_name].append(q)
    return q


def unlisten_event(event_name: str, queue: asyncio.Queue) -> None:
    """Remove a listener."""
    queues = _event_hub.get(event_name, [])
    if queue in queues:
        queues.remove(queue)


class IndicatorCalculatorService:
    """Background service that calculates indicators on candle upsert events.

    Hooks into the event system to auto-calculate when CandleSynchronizer
    produces new candles. Also performs a backfill on startup.
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._analysis = TechnicalAnalysisService()
        self._stats = {"calculated": 0, "skipped": 0, "errors": 0}

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def start(self) -> None:
        if self._running:
            logger.warning("Indicator calculator already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Indicator calculator started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Indicator calculator stopped")

    async def _run(self) -> None:
        """Main loop: backfill on startup, then listen for events."""
        # Backfill existing candles on startup
        await self._backfill_existing()

        # Listen for candle upsert events
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
                    logger.error(f"Event handling error: {e}", exc_info=True)
                    self._stats["errors"] += 1
        finally:
            unlisten_event("candle_upserted", queue)

    async def _backfill_existing(self) -> None:
        """Calculate indicators for all existing candles that don't have them yet."""
        logger.info("Starting indicator backfill for existing candles...")
        async with async_session() as session:
            candle_repo = CandleRepository(session)
            indicator_repo = IndicatorRepository(session)

            for symbol in SUPPORTED_SYMBOLS:
                for tf in SUPPORTED_TIMEFRAMES:
                    try:
                        await self._backfill_symbol_tf(
                            session, candle_repo, indicator_repo, symbol, tf
                        )
                    except Exception as e:
                        logger.error(f"Backfill error for {symbol}/{tf}: {e}")
                        self._stats["errors"] += 1

            await session.commit()
        logger.info(
            f"Indicator backfill complete. "
            f"Calculated: {self._stats['calculated']}, "
            f"Skipped: {self._stats['skipped']}"
        )

    async def _backfill_symbol_tf(
        self,
        session: Any,
        candle_repo: CandleRepository,
        indicator_repo: IndicatorRepository,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Backfill indicators for one symbol+timeframe pair.

        For each indicator calculation, we need enough candles (e.g., 200 EMA needs
        at least 200 candles). We fetch a large batch of candles, then calculate
        indicators for the most recent candle where the calculation is meaningful.
        """
        candles = await candle_repo.get_candles(symbol, timeframe, limit=500)
        if not candles:
            logger.debug(f"No candles to backfill for {symbol}/{timeframe}")
            return

        oldest_needed = max(
            200,  # EMA 200
            50,   # lookback for fib/support-resistance
            26 + 9 + 1,  # MACD
            14 + 1,  # ATR/ADX/RSI
        )

        # Only calculate for candles where we have enough history. Start at
        # oldest_needed - 1 so the FIRST candle with full history (index
        # oldest_needed - 1, i.e. the 200th candle for EMA200) is also
        # calculated — previously the loop started at oldest_needed, which
        # produced ZERO rows for any symbol+timeframe with exactly
        # oldest_needed candles (e.g. a fresh backfill of 200 H1 candles).
        for i in range(max(0, oldest_needed - 1), len(candles)):
            target_candle = candles[i]
            # Skip if already exists
            exists = await indicator_repo.exists(
                symbol, timeframe, target_candle.timestamp
            )
            if exists:
                self._stats["skipped"] += 1
                continue

            # Use candles up to and including target
            window = candles[max(0, i - 300) : i + 1]
            indicator = self._analysis.calculate_all(window, symbol, timeframe)
            if indicator is not None:
                await indicator_repo.upsert(indicator)
                self._stats["calculated"] += 1

    async def _handle_candle_event(self, data: Any) -> None:
        """Handle a candle_upserted event by calculating indicators."""
        # Data can be a dict with symbol, timeframe, timestamp, or a Candle object
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
            indicator_repo = IndicatorRepository(session)

            # Fetch enough candles for indicator calculation
            candles = await candle_repo.get_candles(symbol, timeframe, limit=300)
            if not candles:
                return

            # Check if latest candle already has indicators
            latest_candle = candles[-1]
            exists = await indicator_repo.exists(
                symbol, timeframe, latest_candle.timestamp
            )
            if exists:
                logger.debug(
                    f"Indicators already exist for {symbol}/{timeframe} "
                    f"@{latest_candle.timestamp}"
                )
                return

            indicator = self._analysis.calculate_all(candles, symbol, timeframe)
            if indicator is not None:
                await indicator_repo.upsert(indicator)
                self._stats["calculated"] += 1
                logger.debug(
                    f"Calculated indicators for {symbol}/{timeframe} "
                    f"@{latest_candle.timestamp}"
                )

            await session.commit()
