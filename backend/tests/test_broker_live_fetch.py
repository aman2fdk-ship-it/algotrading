"""Regression coverage for the broker-info live-fetch path (production matrix row 11).

The production pre-deploy matrix found that ``GET /api/v1/broker`` raised
``TypeError: BrokerRepository.upsert_broker() got an unexpected keyword argument 'timezone'``
whenever a *connected* provider had to be queried, and the endpoint's broad
``except Exception`` turned that into a spurious HTTP 503 (plus a 5xx in the
observability counters).  The existing
``tests/test_api.py::TestBrokerEndpoint::test_get_broker_from_db`` covers only the
"snapshot already in the DB" path, which is why the defect escaped the suite.
This test exercises the previously untested live-fetch path.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.services.mt5_client import BrokerData
from app.utils.security import create_access_token, hash_password


class _ConnectedProvider:
    """Minimal stand-in for a connected MarketDataProvider."""

    def __init__(self) -> None:
        self.broker_calls = 0

    async def is_connected(self) -> bool:
        return True

    async def get_broker_info(self) -> BrokerData:
        self.broker_calls += 1
        return BrokerData(
            name="OANDA Practice",
            server="api-fxpractice.oanda.com",
            timezone="UTC",
            regulation="CFTC/NFA",
        )


async def _auth_headers(db_session) -> dict:
    user = User(
        id=str(uuid.uuid4()),
        email="broker-live@example.com",
        hashed_password=hash_password("password123"),
        name="Broker Live",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_broker_live_fetch_returns_200_and_persists(
    client: AsyncClient, db_session, monkeypatch
):
    """A connected provider's broker info is persisted and returned as 200 (not 503)."""
    from app.routers import market_data as market_data_router

    provider = _ConnectedProvider()
    monkeypatch.setattr(market_data_router, "_get_provider", lambda: provider)
    headers = await _auth_headers(db_session)

    response = await client.get("/api/v1/broker", headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == "OANDA Practice"
    assert data["server"] == "api-fxpractice.oanda.com"
    assert data["timezone"] == "UTC"
    assert provider.broker_calls == 1

    # The fetched snapshot must actually be persisted: a second call is served
    # from the database without hitting the provider again.
    second = await client.get("/api/v1/broker", headers=headers)
    assert second.status_code == 200
    assert second.json()["name"] == "OANDA Practice"
    assert provider.broker_calls == 1
