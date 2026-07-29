"""Session Detector — determines the current trading session based on UTC time.

Trading sessions:
- Asian: 00:00 – 09:00 UTC (Tokyo/Sydney)
- London: 08:00 – 17:00 UTC
- New York: 13:00 – 22:00 UTC
- Overlap periods possible (e.g., London + NY 13:00-17:00)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.repositories.market_status_repository import MarketStatusRepository
from app.services.mt5_client import SUPPORTED_SYMBOLS

logger = logging.getLogger(__name__)

DETECT_INTERVAL = 60.0  # Check sessions every 60 seconds

# Session definitions (UTC hours)
SESSIONS = [
    ("Asian", 0, 9),
    ("London", 8, 17),
    ("NY", 13, 22),
]

# Symbols that are closed on weekends (all forex, metals, crypto are 24/7 except forex)
WEEKEND_CLOSED_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "XAUUSD"}


class SessionDetector:
    """Background service that detects the current trading session for each symbol."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            logger.warning("Session detector already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Session detector started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Session detector stopped")

    async def _run(self) -> None:
        while self._running:
            try:
                await self._detect_and_update()
                await asyncio.sleep(DETECT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session detector error: {e}", exc_info=True)
                await asyncio.sleep(10.0)

    async def _detect_and_update(self) -> None:
        """Detect sessions and update market_status table."""
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour

        # Determine active session
        active_session = self._determine_session(hour)
        is_weekend = weekday >= 5  # Saturday/Sunday

        async with async_session() as session:
            repo = MarketStatusRepository(session)

            for symbol in SUPPORTED_SYMBOLS:
                is_closed = False
                session_name = active_session

                # Crypto trades 24/7
                if symbol in ("BTCUSD", "ETHUSD"):
                    is_closed = False
                    session_name = active_session if active_session != "closed" else "Asian"
                elif symbol in WEEKEND_CLOSED_SYMBOLS and is_weekend:
                    is_closed = True
                    session_name = "closed"
                elif active_session == "closed":
                    is_closed = True
                    session_name = "closed"
                else:
                    is_closed = False

                await repo.upsert_status(symbol, not is_closed, session_name)

            await session.commit()

        logger.debug(
            f"Session detection: UTC hour={hour}, weekday={weekday}, "
            f"session={active_session}, weekend={is_weekend}"
        )

    @staticmethod
    def _determine_session(utc_hour: int) -> str:
        """Determine the dominant trading session from UTC hour.

        Priority: NY > London > Asian (during overlaps).
        """
        # NY session check first (overlaps override others)
        if 13 <= utc_hour < 22:
            # During London/NY overlap (13-17), return the combined session
            if 13 <= utc_hour < 17:
                return "London/NY"
            return "NY"
        elif 8 <= utc_hour < 13:
            # During Asian/London overlap (8-9), London dominates
            return "London"
        elif 0 <= utc_hour < 9:
            return "Asian"
        return "closed"
