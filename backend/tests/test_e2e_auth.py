"""End-to-end authentication lifecycle tests for the ForexAI Terminal backend.

Exercises the full auth flow through the HTTP layer against the real
SQLite test DB: register → login → protected access → wrong-token
rejection → refresh rotation, plus cross-user data isolation.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest import BacktestRun

BASE = "/auth"

PASSWORD = "StrongPass123!"


# ── Helpers ────────────────────────────────────────────────────────────────────


def registration(name: str = "E2E Trader", email: str | None = None) -> dict:
    return {
        "name": name,
        "email": email or f"e2e-{uuid.uuid4().hex}@example.com",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }


async def register_user(client: AsyncClient, **overrides) -> dict:
    """Register a user and return the JSON response body."""
    response = await client.post(f"{BASE}/register", json=registration(**overrides))
    assert response.status_code == 201
    return response.json()


def auth_headers_for(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _seed_backtest_run(db_session: AsyncSession, user_id: str) -> None:
    """Seed one completed backtest run owned by `user_id`."""
    db_session.add(
        BacktestRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            symbol="EURUSD",
            timeframe="H1",
            start_date=datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc),
            end_date=datetime(2024, 6, 5, 0, 0, tzinfo=timezone.utc),
            initial_balance=10000.0,
            risk_percentage=1.0,
            final_balance=10500.0,
            total_trades=10,
            win_rate=60.0,
            profit_factor=2.0,
            max_drawdown=5.0,
            expectancy=50.0,
            sharpe_ratio=1.5,
            equity_curve=json.dumps(
                [{"timestamp": "2024-06-01T12:00:00+00:00", "balance": 10200.0}]
            ),
            monthly_performance=json.dumps(
                [{"month": "2024-06", "return_pct": 5.0, "trades": 10, "win_rate": 60.0}]
            ),
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Register → Login
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_returns_tokens(client: AsyncClient):
    """POST /auth/register returns access + refresh tokens."""
    body = await register_user(client)
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_with_registered_credentials_returns_tokens(client: AsyncClient):
    """POST /auth/login with the registered credentials returns fresh tokens."""
    payload = registration()
    await client.post(f"{BASE}/register", json=payload)

    response = await client.post(
        f"{BASE}/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    """Login with a wrong password is rejected."""
    payload = registration()
    await client.post(f"{BASE}/register", json=payload)

    response = await client.post(
        f"{BASE}/login", json={"email": payload["email"], "password": "WrongPass123!"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    """Registering the same email twice is rejected with a conflict."""
    payload = registration()
    await client.post(f"{BASE}/register", json=payload)
    response = await client.post(f"{BASE}/register", json=payload)
    assert response.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════════
# Access token → protected endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_access_token_calls_protected_endpoint(client: AsyncClient):
    """The access token from register works on a protected endpoint."""
    body = await register_user(client)

    response = await client.get(f"{BASE}/me", headers=auth_headers_for(body["access_token"]))
    assert response.status_code == 200
    assert response.json()["email"]
    assert response.json()["is_active"] is True


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_returns_401(client: AsyncClient):
    """Protected endpoints reject requests without any token."""
    assert (await client.get(f"{BASE}/me")).status_code == 401
    assert (await client.get("/api/v1/symbols")).status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401(client: AsyncClient):
    """A garbage token is rejected by protected endpoints."""
    response = await client.get(
        f"{BASE}/me", headers=auth_headers_for("not.a.real.jwt.token")
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tampered_token_returns_401(client: AsyncClient):
    """A token with one flipped character is rejected."""
    body = await register_user(client)
    token = body["access_token"]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    response = await client.get(f"{BASE}/me", headers=auth_headers_for(tampered))
    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Refresh token flow
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient):
    """A refresh token rotates into new tokens that work on protected endpoints."""
    body = await register_user(client)

    response = await client.post(
        f"{BASE}/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["access_token"]
    assert rotated["refresh_token"]

    # The rotated access token must work immediately
    me = await client.get(f"{BASE}/me", headers=auth_headers_for(rotated["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == (await client.get(
        f"{BASE}/me", headers=auth_headers_for(body["access_token"])
    )).json()["email"]


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client: AsyncClient):
    """An access token cannot be used as a refresh token."""
    body = await register_user(client)
    response = await client.post(
        f"{BASE}/refresh", json={"refresh_token": body["access_token"]}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_garbage_token_rejected(client: AsyncClient):
    """A garbage refresh token is rejected."""
    response = await client.post(f"{BASE}/refresh", json={"refresh_token": "garbage"})
    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-user data isolation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_second_user_cannot_see_first_users_data(
    client: AsyncClient, db_session: AsyncSession
):
    """User B must not see backtest runs belonging to user A."""
    # User A registers and gets a backtest run.
    user_a = await register_user(client, name="User A")
    me_a = await client.get(f"{BASE}/me", headers=auth_headers_for(user_a["access_token"]))
    assert me_a.status_code == 200
    user_a_id = me_a.json()["id"]

    _seed_backtest_run(db_session, user_a_id)
    await db_session.commit()

    # User B registers.
    user_b = await register_user(client, name="User B")
    me_b = await client.get(f"{BASE}/me", headers=auth_headers_for(user_b["access_token"]))
    user_b_id = me_b.json()["id"]
    assert user_b_id != user_a_id

    # B sees no runs; A sees exactly their own run.
    runs_b = await client.get(
        "/api/v1/backtest/runs", headers=auth_headers_for(user_b["access_token"])
    )
    assert runs_b.status_code == 200
    assert runs_b.json()["count"] == 0
    assert runs_b.json()["runs"] == []

    runs_a = await client.get(
        "/api/v1/backtest/runs", headers=auth_headers_for(user_a["access_token"])
    )
    assert runs_a.status_code == 200
    assert runs_a.json()["count"] == 1
    assert runs_a.json()["runs"][0]["user_id"] == user_a_id
