"""SMCRepository — persistence operations for SMCStructure."""

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.smc_structure import SMCStructure

logger = logging.getLogger(__name__)


class SMCRepository:
    """Repository for SMCStructure model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, structure: SMCStructure) -> SMCStructure:
        """Insert or update an SMC structure by unique constraint.

        Deduplication key: symbol + timeframe + timestamp + structure_type + direction.
        """
        existing = await self._session.execute(
            select(SMCStructure).where(
                and_(
                    SMCStructure.symbol == structure.symbol,
                    SMCStructure.timeframe == structure.timeframe,
                    SMCStructure.timestamp == structure.timestamp,
                    SMCStructure.structure_type == structure.structure_type,
                    SMCStructure.direction == structure.direction,
                )
            )
        )
        existing_struct = existing.scalar_one_or_none()

        if existing_struct:
            existing_struct.price_low = structure.price_low
            existing_struct.price_high = structure.price_high
            existing_struct.price_mid = structure.price_mid
            existing_struct.key_level = structure.key_level
            existing_struct.confidence = structure.confidence
            existing_struct.details = structure.details
            await self._session.flush()
            return existing_struct
        else:
            self._session.add(structure)
            await self._session.flush()
            return structure

    async def exists(
        self,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        structure_type: str,
        direction: str,
    ) -> bool:
        """Check if a structure already exists."""
        result = await self._session.execute(
            select(SMCStructure).where(
                and_(
                    SMCStructure.symbol == symbol,
                    SMCStructure.timeframe == timeframe,
                    SMCStructure.timestamp == timestamp,
                    SMCStructure.structure_type == structure_type,
                    SMCStructure.direction == direction,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_type(
        self,
        symbol: str,
        timeframe: str,
        structure_type: str,
        limit: int = 50,
    ) -> Sequence[SMCStructure]:
        """Get structures of a specific type."""
        stmt = (
            select(SMCStructure)
            .where(
                and_(
                    SMCStructure.symbol == symbol,
                    SMCStructure.timeframe == timeframe,
                    SMCStructure.structure_type == structure_type,
                )
            )
            .order_by(SMCStructure.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        structures = result.scalars().all()
        return list(reversed(structures))

    async def get_all(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 50,
    ) -> Sequence[SMCStructure]:
        """Get all SMC structures for a symbol+timeframe."""
        stmt = (
            select(SMCStructure)
            .where(
                and_(
                    SMCStructure.symbol == symbol,
                    SMCStructure.timeframe == timeframe,
                )
            )
            .order_by(SMCStructure.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        structures = result.scalars().all()
        return list(reversed(structures))

    async def get_latest(
        self,
        symbol: str,
        timeframe: str,
        structure_type: str,
    ) -> SMCStructure | None:
        """Get the most recent structure of a given type."""
        stmt = (
            select(SMCStructure)
            .where(
                and_(
                    SMCStructure.symbol == symbol,
                    SMCStructure.timeframe == timeframe,
                    SMCStructure.structure_type == structure_type,
                )
            )
            .order_by(SMCStructure.timestamp.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
