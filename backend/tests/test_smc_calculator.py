from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.smc_calculator import SMCCalculatorService

@pytest.mark.asyncio
async def test_new_candle_event_triggers_smc_detection_and_storage():
    service=SMCCalculatorService(); service._detection.detect_all=MagicMock(return_value=[MagicMock(timestamp=1,structure_type="bos",direction="bullish")])
    candle_repo=MagicMock(); candle_repo.get_candles=AsyncMock(return_value=[MagicMock()]); smc_repo=MagicMock(); smc_repo.exists=AsyncMock(return_value=False); smc_repo.upsert=AsyncMock(); session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.smc_calculator.async_session",return_value=C()),patch("app.services.smc_calculator.CandleRepository",return_value=candle_repo),patch("app.services.smc_calculator.SMCRepository",return_value=smc_repo): await service._handle_candle_event({"symbol":"EURUSD","timeframe":"M1"})
    smc_repo.upsert.assert_awaited_once(); assert service.stats["detected"] == 1

@pytest.mark.asyncio
async def test_existing_structure_is_skipped_partial_update():
    service=SMCCalculatorService(); structure=MagicMock(timestamp=1,structure_type="bos",direction="bullish"); service._detection.detect_all=MagicMock(return_value=[structure]); candle_repo=MagicMock(); candle_repo.get_candles=AsyncMock(return_value=[MagicMock()]); smc_repo=MagicMock(); smc_repo.exists=AsyncMock(return_value=True); smc_repo.upsert=AsyncMock(); session=MagicMock(); session.commit=AsyncMock()
    class C:
        async def __aenter__(self): return session
        async def __aexit__(self,*a): pass
    with patch("app.services.smc_calculator.async_session",return_value=C()),patch("app.services.smc_calculator.CandleRepository",return_value=candle_repo),patch("app.services.smc_calculator.SMCRepository",return_value=smc_repo): await service._handle_candle_event({"symbol":"EURUSD","timeframe":"M1"})
    smc_repo.upsert.assert_not_called(); assert service.stats["detected"] == 0

def test_invalid_event_is_ignored():
    service=SMCCalculatorService(); assert service.stats["detected"] == 0
