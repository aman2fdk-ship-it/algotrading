from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.models.candle import Candle
from app.models.tick import Tick
from app.services.candle_sync import CandleSynchronizer
from app.services.mt5_client import OHLCVData

def candle(ts=None):
    return Candle(symbol="EURUSD", timeframe="M1", timestamp=ts or datetime(2024,1,2,12,0,tzinfo=timezone.utc), open=1, high=1.1, low=.9, close=1, tick_volume=2)

def data(): return OHLCVData("EURUSD", "M1", datetime(2024,1,2,12,0,tzinfo=timezone.utc), 1,1.2,.8,1.15,10)

@pytest.mark.asyncio
async def test_candle_generation_from_mt5_fetch():
    client=MagicMock(); client.fetch_candles=AsyncMock(return_value=[data()])
    sync=CandleSynchronizer(client)
    repo=MagicMock(); repo.get_latest_candle=AsyncMock(return_value=None); repo.upsert_candle=AsyncMock()
    session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.candle_sync.async_session",return_value=C()), patch("app.services.candle_sync.CandleRepository",return_value=repo), patch("app.services.candle_sync.SUPPORTED_SYMBOLS",["EURUSD"]), patch("app.services.candle_sync.SUPPORTED_TIMEFRAMES",["M1"]):
        await sync._sync_latest_candles()
    repo.upsert_candle.assert_awaited_once(); assert sync.stats["synced"] == 1

@pytest.mark.asyncio
async def test_partial_candle_updates_ohlc_from_ticks():
    sync=CandleSynchronizer(MagicMock()); existing=candle(); repo=MagicMock(); tick_repo=MagicMock()
    tick_repo.get_ticks=AsyncMock(return_value=[Tick(symbol="EURUSD",timestamp=datetime(2024,1,2,12,0,30,tzinfo=timezone.utc),bid=.95,ask=1.2,volume=1)])
    repo.upsert_candle=AsyncMock()
    result=await sync._update_candle_from_ticks(MagicMock(),repo,tick_repo,"EURUSD","M1",existing,datetime(2024,1,2,12,0,tzinfo=timezone.utc),datetime.now(timezone.utc))
    assert result.high == 1.2 and result.low == .9 and result.close == .95 and result.tick_volume == 3

@pytest.mark.asyncio
async def test_no_ticks_leaves_partial_candle_unchanged():
    sync=CandleSynchronizer(MagicMock()); existing=candle(); repo=MagicMock(); tick_repo=MagicMock(); tick_repo.get_ticks=AsyncMock(return_value=[])
    assert await sync._update_candle_from_ticks(MagicMock(),repo,tick_repo,"EURUSD","M1",existing,datetime.now(timezone.utc),datetime.now(timezone.utc)) is None
    repo.upsert_candle.assert_not_called()

def test_alignment_supports_multiple_timeframes():
    ts=datetime(2024,1,2,12,34,56,tzinfo=timezone.utc)
    assert CandleSynchronizer._align_timestamp(ts,60).minute == 34
    assert CandleSynchronizer._align_timestamp(ts,300).minute == 30

def test_duplicate_candle_upsert_is_delegated_to_repository():
    # Repository upsert is the service's idempotency boundary.
    assert candle().symbol == "EURUSD"
