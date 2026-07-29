"""Candle Synchronizer — builds/updates OHLCV candles from tick data.

For each symbol and timeframe, builds candles by querying the latest tick data
and storing aggregated OHLCV rows. Pulls historical candles from MT5 on startup.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.candle import Candle
from app.models.tick import Tick
from app.repositories.candle_repository import CandleRepository
from app.repositories.tick_repository import TickRepository
from app.services.mt5_client import (
    MT5ClientProtocol, SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES, OHLCVData,
)

logger = logging.getLogger(__name__)

SYNC_INTERVAL = 30.0  # Sync candles every 30 seconds
INITIAL_BACKFILL_COUNT = 200  # Number of candles to backfill on startup

# Seconds per timeframe for boundary alignment
TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


class CandleSynchronizer:
    """Background service that syncs candles from ticks and MT5 historical data."""

    def __init__(self, mt5_client: MT5ClientProtocol) -> None:
        self._client = mt5_client
        self._running = False
        self._task: asyncio.Task | None = None
        self._stats = {"synced": 0, "errors": 0}

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def start(self) -> None:
        if self._running:
            logger.warning("Candle synchronizer already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Candle synchronizer started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Candle synchronizer stopped")

    async def _run(self) -> None:
        """Main sync loop."""
        # Initial backfill from MT5 historical data
        await self._backfill_historical()

        while self._running:
            try:
                if await self._client.is_connected():
                    await self._sync_latest_candles()
                await asyncio.sleep(SYNC_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Candle sync error: {e}", exc_info=True)
                self._stats["errors"] += 1
                await asyncio.sleep(5.0)

    async def _backfill_historical(self) -> None:
        """Fetch historical candles from MT5 on startup."""
        logger.info("Starting historical candle backfill...")
        async with async_session() as session:
            candle_repo = CandleRepository(session)
            for symbol in SUPPORTED_SYMBOLS:
                for tf in SUPPORTED_TIMEFRAMES:
                    try:
                        # Check if we already have data
                        latest = await candle_repo.get_latest_candle(symbol, tf)
                        if latest and (datetime.now(timezone.utc) - latest.timestamp).total_seconds() < TF_SECONDS[tf]:
                            logger.debug(f"Skipping backfill for {symbol}/{tf} — data is current")
                            continue

                        candles = await self._client.fetch_candles(symbol, tf, INITIAL_BACKFILL_COUNT)
                        if candles:
                            db_candles = [
                                Candle(
                                    symbol=c.symbol,
                                    timeframe=c.timeframe,
                                    timestamp=c.timestamp,
                                    open=c.open,
                                    high=c.high,
                                    low=c.low,
                                    close=c.close,
                                    tick_volume=c.tick_volume,
                                    real_volume=c.real_volume,
                                    spread=c.spread,
                                )
                                for c in candles
                            ]
                            await candle_repo.upsert_candles(db_candles)
                            self._stats["synced"] += len(db_candles)
                            logger.info(f"Backfilled {len(db_candles)} candles for {symbol}/{tf}")
                    except Exception as e:
                        logger.error(f"Backfill error for {symbol}/{tf}: {e}")
                        self._stats["errors"] += 1
            await session.commit()
        logger.info(f"Historical backfill complete. Synced: {self._stats['synced']} candles")

    async def _sync_latest_candles(self) -> None:
        """Build the latest candle for each symbol/timeframe from ticks."""
        async with async_session() as session:
            candle_repo = CandleRepository(session)
            tick_repo = TickRepository(session)

            for symbol in SUPPORTED_SYMBOLS:
                for tf in SUPPORTED_TIMEFRAMES:
                    try:
                        latest_candle = await candle_repo.get_latest_candle(symbol, tf)
                        now = datetime.now(timezone.utc)
                        tf_secs = TF_SECONDS[tf]

                        # Determine the current candle boundary
                        current_boundary = self._align_timestamp(now, tf_secs)

                        if latest_candle and latest_candle.timestamp >= current_boundary:
                            # Current candle exists — update it from ticks
                            updated = await self._update_candle_from_ticks(
                                session, candle_repo, tick_repo,
                                symbol, tf, latest_candle, current_boundary, now,
                            )
                            if updated:
                                self._emit_candle_event(updated)
                        elif not latest_candle or latest_candle.timestamp < current_boundary:
                            # Need a new candle — try fetching from MT5
                            candles = await self._client.fetch_candles(symbol, tf, 1)
                            if candles:
                                latest = candles[-1]
                                db_candle = Candle(
                                    symbol=latest.symbol,
                                    timeframe=latest.timeframe,
                                    timestamp=latest.timestamp,
                                    open=latest.open,
                                    high=latest.high,
                                    low=latest.low,
                                    close=latest.close,
                                    tick_volume=latest.tick_volume,
                                    real_volume=latest.real_volume,
                                    spread=latest.spread,
                                )
                                await candle_repo.upsert_candle(db_candle)
                                self._stats["synced"] += 1
                                self._emit_candle_event(db_candle)

                    except Exception as e:
                        logger.error(f"Sync error for {symbol}/{tf}: {e}")
                        self._stats["errors"] += 1

            await session.commit()

    async def _update_candle_from_ticks(
        self,
        session: AsyncSession,
        candle_repo: CandleRepository,
        tick_repo: TickRepository,
        symbol: str,
        timeframe: str,
        candle: Candle,
        boundary: datetime,
        now: datetime,
    ) -> Candle | None:
        """Update an existing candle's OHLCV from ticks since the last update.

        Returns the updated candle if changes were made, None otherwise.
        """
        # Get ticks in the current candle window
        ticks = await tick_repo.get_ticks(symbol, limit=1000)
        relevant_ticks = [t for t in ticks if t.timestamp >= boundary]

        if not relevant_ticks:
            return None

        # Calculate OHLC from ticks
        highs = [t.ask for t in relevant_ticks]
        lows = [t.bid for t in relevant_ticks]
        closes = [t.bid for t in relevant_ticks]  # close = last bid

        candle.high = max(candle.high, max(highs))
        candle.low = min(candle.low, min(lows))
        candle.close = closes[-1]
        candle.tick_volume += len(relevant_ticks)
        # Note: candle.open doesn't change once set

        await candle_repo.upsert_candle(candle)
        self._stats["synced"] += 1
        return candle

    @staticmethod
    def _align_timestamp(ts: datetime, seconds: int) -> datetime:
        """Align a datetime to the start of the candle boundary."""
        epoch = ts.timestamp()
        aligned = int(epoch / seconds) * seconds
        return datetime.fromtimestamp(aligned, tz=timezone.utc)

    @staticmethod
    def _emit_candle_event(candle: Candle) -> None:
        """Emit a candle_upserted event for downstream services."""
        try:
            from app.services.indicator_calculator import emit_event
            emit_event("candle_upserted", {
                "symbol": candle.symbol,
                "timeframe": candle.timeframe,
                "timestamp": candle.timestamp.isoformat(),
            })
        except ImportError:
            pass
