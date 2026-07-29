import logging
from datetime import datetime, timezone as tz

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import AccountInfo

logger = logging.getLogger(__name__)


class AccountRepository:
    """Repository for AccountInfo model operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_latest(self) -> AccountInfo | None:
        result = await self._session.execute(
            select(AccountInfo).order_by(AccountInfo.last_updated.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert_account(
        self,
        balance: float,
        equity: float,
        margin: float,
        free_margin: float,
        leverage: int,
        currency: str,
        name: str | None = None,
        server: str | None = None,
        login: int | None = None,
    ) -> AccountInfo:
        """Create a new account snapshot. Always inserts a new row for history."""
        account = AccountInfo(
            balance=balance,
            equity=equity,
            margin=margin,
            free_margin=free_margin,
            leverage=leverage,
            currency=currency,
            name=name,
            server=server,
            login=login,
            last_updated=datetime.now(tz.utc),
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def prune_old(self, keep: int = 100) -> int:
        """Delete old account snapshots, keeping the most recent `keep`."""
        subq = (
            select(AccountInfo.id)
            .order_by(AccountInfo.last_updated.desc())
            .limit(keep)
        )
        stmt = select(func.count()).select_from(AccountInfo).where(
            AccountInfo.id.not_in(subq)
        )
        result = await self._session.execute(stmt)
        count = result.scalar() or 0
        from sqlalchemy import delete

        d_stmt = delete(AccountInfo).where(AccountInfo.id.not_in(subq))
        await self._session.execute(d_stmt)
        await self._session.flush()
        logger.debug(f"Pruned {count} old account snapshots")
        return count
