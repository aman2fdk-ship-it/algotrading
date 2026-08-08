"""Unit tests for the live tick collection loop."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.mt5_client import TickData
from app.services.tick_collector import LiveTickCollector


def tick(symbol="EURUSD", second=0):
    return TickData(symbol, datetime(2024, 1, 2, 12, 0, second, tzinfo=timezone.utc), 1.1, 1.1002, 2, 5)

@pytest.mark.asyncio
async def test_ticks_are_received_and_stored():
    client = MagicMock()
    client.get_current_tick = AsyncMock(return_value=tick())
    collector = LiveTickCollector(client)
    repo = MagicMock(); repo.upsert_tick = AsyncMock()
    session = MagicMock(); session.commit = AsyncMock()
    class Context:
        async def __aenter__(self): return session
        async def __aexit__(self, *args): pass
    with patch("app.services.tick_collector.async_session", return_value=Context()), patch("app.services.tick_collector.TickRepository", return_value=repo):
        await collector._persist_ticks([tick()])
    repo.upsert_tick.assert_awaited_once()
    assert collector.stats["written"] == 1

@pytest.mark.asyncio
async def test_duplicate_tick_is_counted_as_skipped():
    collector = LiveTickCollector(MagicMock())
    repo = MagicMock(); repo.upsert_tick = AsyncMock(side_effect=Exception("duplicate"))
    session = MagicMock(); session.commit = AsyncMock()
    class Context:
        async def __aenter__(self): return session
        async def __aexit__(self, *args): pass
    with patch("app.services.tick_collector.async_session", return_value=Context()), patch("app.services.tick_collector.TickRepository", return_value=repo):
        await collector._persist_ticks([tick()])
    assert collector.stats["skipped"] == 1

@pytest.mark.asyncio
async def test_symbol_filtering_uses_supported_symbols_only():
    client = MagicMock(); client.get_current_tick = AsyncMock(side_effect=lambda symbol: tick(symbol))
    collector = LiveTickCollector(client)
    with patch("app.services.tick_collector.SUPPORTED_SYMBOLS", ["EURUSD", "GBPUSD"]):
        await collector._get_tick("EURUSD")
        await collector._get_tick("GBPUSD")
    assert [c.args[0] for c in client.get_current_tick.await_args_list] == ["EURUSD", "GBPUSD"]

@pytest.mark.asyncio
async def test_disconnected_mt5_does_not_fetch():
    client = MagicMock(); client.is_connected = AsyncMock(return_value=False); client.get_current_tick = AsyncMock()
    collector = LiveTickCollector(client)
    async def stop_after_poll(*args):
        collector._running = False
    with patch("app.services.tick_collector.asyncio.sleep", new=stop_after_poll), patch("app.services.tick_collector.SUPPORTED_SYMBOLS", ["EURUSD"]):
        collector._running = True
        await collector._run()
    client.get_current_tick.assert_not_awaited()

@pytest.mark.asyncio
async def test_stop_cancels_background_task_gracefully():
    collector = LiveTickCollector(MagicMock())
    collector._task = __import__('asyncio').create_task(__import__('asyncio').sleep(60))
    collector._running = True
    await collector.stop()
    assert collector._running is False and collector._task.done()
