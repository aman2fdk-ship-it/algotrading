from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.market_status import MarketStatusMonitor

@pytest.mark.asyncio
async def test_available_symbols_are_open_and_missing_symbols_closed():
    client=MagicMock(); client.get_symbols=AsyncMock(return_value=["EURUSD"]); monitor=MarketStatusMonitor(client)
    repo=MagicMock(); repo.get_by_symbol=AsyncMock(return_value=None); repo.upsert_status=AsyncMock(); session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.market_status.async_session",return_value=C()), patch("app.services.market_status.MarketStatusRepository",return_value=repo), patch("app.services.market_status.SUPPORTED_SYMBOLS",["EURUSD","GBPUSD"]): await monitor._check_symbols()
    assert repo.upsert_status.await_args_list[0].args[:2] == ("EURUSD",True); assert repo.upsert_status.await_args_list[1].args[:2] == ("GBPUSD",False)

@pytest.mark.asyncio
async def test_source_error_does_not_update_status():
    client=MagicMock(); client.get_symbols=AsyncMock(side_effect=ConnectionError()); monitor=MarketStatusMonitor(client)
    with patch("app.services.market_status.async_session") as session: await monitor._check_symbols(); session.assert_not_called()

@pytest.mark.asyncio
async def test_open_to_closed_transition_is_persisted():
    client=MagicMock(); client.get_symbols=AsyncMock(return_value=[]); monitor=MarketStatusMonitor(client); current=MagicMock(is_open=True,session="London")
    repo=MagicMock(); repo.get_by_symbol=AsyncMock(return_value=current); repo.upsert_status=AsyncMock(); session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.market_status.async_session",return_value=C()),patch("app.services.market_status.MarketStatusRepository",return_value=repo),patch("app.services.market_status.SUPPORTED_SYMBOLS",["EURUSD"]): await monitor._check_symbols()
    repo.upsert_status.assert_awaited_once_with("EURUSD",False,"London")
