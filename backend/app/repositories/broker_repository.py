import logging
from datetime import datetime, timezone as tz

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import BrokerInfo

logger = logging.getLogger(__name__)


class BrokerRepository:
    """Repository for BrokerInfo model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_latest(self) -> BrokerInfo | None:
        result = await self._session.execute(
            select(BrokerInfo).order_by(BrokerInfo.last_updated.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert_broker(
        self,
        name: str,
        server: str,
        broker_timezone: str,
        regulation: str | None = None,
    ) -> BrokerInfo:
        """Create a new broker info snapshot."""
        broker = BrokerInfo(
            name=name,
            server=server,
            timezone=broker_timezone,
            regulation=regulation,
            last_updated=datetime.now(tz.utc),
        )
        self._session.add(broker)
        await self._session.flush()
        return broker

    async def prune_old(self, keep: int = 50) -> int:
        """Delete old broker snapshots, keeping the most recent `keep`."""
        subq = (
            select(BrokerInfo.id)
            .order_by(BrokerInfo.last_updated.desc())
            .limit(keep)
        )
        from sqlalchemy import delete

        d_stmt = delete(BrokerInfo).where(BrokerInfo.id.not_in(subq))
        result = await self._session.execute(d_stmt)
        await self._session.flush()
        return result.rowcount or 0
