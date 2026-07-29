"""Reconnection Manager — monitors MT5 connection and auto-reconnects with exponential backoff.

Features:
- Connection health monitoring via heartbeat
- Exponential backoff on reconnection (1s → 2s → 4s → ... → max 60s)
- Maximum retry attempts before giving up
- Structured logging for all connection events
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.services.mt5_client import MT5ClientProtocol

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10.0  # Check connection every 10 seconds
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds
BACKOFF_MULTIPLIER = 2.0
MAX_RETRIES = 10


class ReconnectionManager:
    """Background service that monitors MT5 connection and auto-reconnects."""

    def __init__(
        self,
        mt5_client: MT5ClientProtocol,
        heartbeat_interval: float = HEARTBEAT_INTERVAL,
        initial_backoff: float = INITIAL_BACKOFF,
        max_backoff: float = MAX_BACKOFF,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._client = mt5_client
        self._heartbeat_interval = heartbeat_interval
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._max_retries = max_retries
        self._running = False
        self._task: asyncio.Task | None = None
        self._consecutive_failures = 0
        self._last_connected: datetime | None = None
        self._total_disconnections = 0

    @property
    def stats(self) -> dict:
        return {
            "consecutive_failures": self._consecutive_failures,
            "last_connected": self._last_connected.isoformat() if self._last_connected else None,
            "total_disconnections": self._total_disconnections,
        }

    async def start(self) -> None:
        if self._running:
            logger.warning("Reconnection manager already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Reconnection manager started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Reconnection manager stopped")

    async def _run(self) -> None:
        while self._running:
            try:
                connected = await self._client.heartbeat()

                if connected:
                    if self._consecutive_failures > 0:
                        logger.info(
                            f"MT5 connection restored after {self._consecutive_failures} failures"
                        )
                    self._consecutive_failures = 0
                    self._last_connected = datetime.now(timezone.utc)
                else:
                    self._consecutive_failures += 1
                    self._total_disconnections += 1
                    logger.warning(
                        f"MT5 connection lost (failure {self._consecutive_failures}/{self._max_retries})"
                    )
                    await self._attempt_reconnect()

                await asyncio.sleep(self._heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnection manager error: {e}", exc_info=True)
                self._consecutive_failures += 1
                await asyncio.sleep(self._heartbeat_interval)

    async def _attempt_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._consecutive_failures > self._max_retries:
            logger.error(
                f"Exceeded max retries ({self._max_retries}). Giving up on auto-reconnect."
            )
            return

        backoff = min(
            self._initial_backoff * (self._BACKOFF_MULTIPLIER ** (self._consecutive_failures - 1)),
            self._max_backoff,
        )

        logger.info(f"Attempting MT5 reconnect in {backoff:.1f}s...")
        await asyncio.sleep(backoff)

        try:
            connected = await self._client.connect()
            if connected:
                logger.info("MT5 reconnected successfully")
                self._consecutive_failures = 0
                self._last_connected = datetime.now(timezone.utc)
            else:
                logger.warning(f"MT5 reconnection attempt {self._consecutive_failures} failed")
        except Exception as e:
            logger.error(f"MT5 reconnection error: {e}")

    @property
    def _BACKOFF_MULTIPLIER(self) -> float:
        return BACKOFF_MULTIPLIER
