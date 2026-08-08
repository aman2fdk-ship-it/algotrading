from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.reconnection import ReconnectionManager

@pytest.mark.asyncio
async def test_reconnect_attempt_after_disconnect():
    client=MagicMock(); client.connect=AsyncMock(return_value=True); manager=ReconnectionManager(client,initial_backoff=0)
    manager._consecutive_failures=1
    with patch("app.services.reconnection.asyncio.sleep",new=AsyncMock()): await manager._attempt_reconnect()
    client.connect.assert_awaited_once(); assert manager.stats["consecutive_failures"] == 0

@pytest.mark.asyncio
async def test_exponential_backoff_is_capped():
    client=MagicMock(); client.connect=AsyncMock(return_value=False); manager=ReconnectionManager(client,initial_backoff=2,max_backoff=5); manager._consecutive_failures=3
    with patch("app.services.reconnection.asyncio.sleep",new=AsyncMock()) as sleep: await manager._attempt_reconnect()
    sleep.assert_awaited_once_with(5)

@pytest.mark.asyncio
async def test_max_retry_limit_prevents_connect():
    client=MagicMock(); client.connect=AsyncMock(); manager=ReconnectionManager(client,max_retries=2); manager._consecutive_failures=3
    await manager._attempt_reconnect(); client.connect.assert_not_awaited()

@pytest.mark.asyncio
async def test_temporary_failure_then_success():
    client=MagicMock(); client.connect=AsyncMock(side_effect=[False,True]); manager=ReconnectionManager(client,initial_backoff=0); manager._consecutive_failures=1
    with patch("app.services.reconnection.asyncio.sleep",new=AsyncMock()):
        await manager._attempt_reconnect(); assert manager.stats["consecutive_failures"] == 1
        manager._consecutive_failures=2; await manager._attempt_reconnect()
    assert manager.stats["consecutive_failures"] == 0
