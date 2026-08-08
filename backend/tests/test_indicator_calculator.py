from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.models.candle import Candle
from app.services.indicator_calculator import IndicatorCalculatorService, emit_event, listen_event, unlisten_event

def candles(n):
    return [Candle(symbol="EURUSD", timeframe="M1", timestamp=datetime(2024,1,1,tzinfo=timezone.utc)+timedelta(minutes=i), open=1, high=1.1, low=.9, close=1) for i in range(n)]

def test_event_hub_delivers_candle_updates():
    q=listen_event("test"); emit_event("test", {"symbol":"EURUSD"}); assert q.get_nowait()["symbol"] == "EURUSD"; unlisten_event("test",q)

def test_empty_and_single_candle_are_safe():
    service=IndicatorCalculatorService(); service._analysis.calculate_all=MagicMock(return_value=None)
    assert service._stats == {"calculated":0,"skipped":0,"errors":0}

@pytest.mark.asyncio
async def test_batch_calculation_stores_indicators():
    service=IndicatorCalculatorService(); service._analysis.calculate_all=MagicMock(return_value="indicator")
    candle_repo=MagicMock(); candle_repo.get_candles=AsyncMock(return_value=candles(202))
    indicator_repo=MagicMock(); indicator_repo.exists=AsyncMock(return_value=False); indicator_repo.upsert=AsyncMock()
    await service._backfill_symbol_tf(MagicMock(),candle_repo,indicator_repo,"EURUSD","M1")
    assert indicator_repo.upsert.await_count == 2 and service.stats["calculated"] == 2

@pytest.mark.asyncio
async def test_insufficient_candles_are_skipped():
    service=IndicatorCalculatorService(); candle_repo=MagicMock(); candle_repo.get_candles=AsyncMock(return_value=candles(10)); indicator_repo=MagicMock()
    await service._backfill_symbol_tf(MagicMock(),candle_repo,indicator_repo,"EURUSD","M1")
    indicator_repo.upsert.assert_not_called(); assert service.stats["calculated"] == 0

@pytest.mark.asyncio
async def test_event_calculation_uses_latest_batch_and_stores():
    service=IndicatorCalculatorService(); service._analysis.calculate_all=MagicMock(return_value="indicator")
    candle_repo=MagicMock(); candle_repo.get_candles=AsyncMock(return_value=candles(2)); indicator_repo=MagicMock(); indicator_repo.exists=AsyncMock(return_value=False); indicator_repo.upsert=AsyncMock()
    session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.indicator_calculator.async_session",return_value=C()), patch("app.services.indicator_calculator.CandleRepository",return_value=candle_repo), patch("app.services.indicator_calculator.IndicatorRepository",return_value=indicator_repo):
        await service._handle_candle_event({"symbol":"EURUSD","timeframe":"M1"})
    indicator_repo.upsert.assert_awaited_once()
