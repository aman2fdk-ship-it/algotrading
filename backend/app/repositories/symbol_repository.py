import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.symbol import Symbol

logger = logging.getLogger(__name__)


class SymbolRepository:
    """Repository for Symbol model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all(self) -> Sequence[Symbol]:
        result = await self._session.execute(select(Symbol).order_by(Symbol.code))
        return result.scalars().all()

    async def get_by_code(self, code: str) -> Symbol | None:
        result = await self._session.execute(select(Symbol).where(Symbol.code == code))
        return result.scalar_one_or_none()

    async def get_enabled(self) -> Sequence[Symbol]:
        result = await self._session.execute(
            select(Symbol).where(Symbol.enabled == True).order_by(Symbol.code)
        )
        return result.scalars().all()

    async def upsert(self, symbol: Symbol) -> Symbol:
        existing = await self.get_by_code(symbol.code)
        if existing:
            existing.name = symbol.name
            existing.asset_type = symbol.asset_type
            existing.pip_size = symbol.pip_size
            existing.digits = symbol.digits
            existing.enabled = symbol.enabled
            await self._session.flush()
            return existing
        self._session.add(symbol)
        await self._session.flush()
        return symbol

    async def bulk_upsert(self, symbols: list[Symbol]) -> list[Symbol]:
        results = []
        for sym in symbols:
            results.append(await self.upsert(sym))
        return results
