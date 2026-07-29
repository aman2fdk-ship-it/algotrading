"""Integration tests for Risk Management API endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_test_user(db_session) -> User:
    from app.utils.security import hash_password

    user = User(
        id=str(uuid.uuid4()),
        email=f"risk_test_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("password123"),
        name="Risk Test User",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_headers_for(user: User) -> dict:
    from app.utils.security import create_access_token

    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ── /calculate ────────────────────────────────────────────────────────────────


class TestRiskCalculate:
    @pytest.mark.asyncio
    async def test_full_calculation(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 1.0850,
                "stop_loss": 1.0820,
                "symbol": "EURUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["risk_amount"] == 100.0
        assert data["stop_loss_pips"] == 30.0
        assert "position_size" in data
        assert "lot_size" in data
        assert "mini_lots" in data
        assert "micro_lots" in data
        assert "required_margin" in data
        assert data["take_profit_1"] is not None
        assert data["take_profit_2"] is not None
        assert data["potential_profit_tp1"] is not None
        assert data["risk_reward_ratio_tp1"] == 1.5
        assert "pip_size" in data
        assert "pip_value" in data

    @pytest.mark.asyncio
    async def test_short_trade(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 5000.0,
                "risk_percentage": 2.0,
                "entry_price": 1.0800,
                "stop_loss": 1.0830,
                "symbol": "EURUSD",
                "leverage": 50,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_loss_pips"] == 30.0
        assert data["risk_amount"] == 100.0
        # Short trade — TPs below entry
        assert data["take_profit_1"] < data["entry_price"]
        assert data["take_profit_2"] < data["take_profit_1"]

    @pytest.mark.asyncio
    async def test_usdjpy(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 150.00,
                "stop_loss": 149.50,
                "symbol": "USDJPY",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_loss_pips"] == 50.0

    @pytest.mark.asyncio
    async def test_xauusd(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 20000.0,
                "risk_percentage": 1.0,
                "entry_price": 1900.00,
                "stop_loss": 1890.00,
                "symbol": "XAUUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_loss_pips"] == 100.0
        assert data["pip_size"] == 0.10
        assert data["pip_value"] == 10.0

    @pytest.mark.asyncio
    async def test_btcusd(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 5000.0,
                "risk_percentage": 2.0,
                "entry_price": 50000.0,
                "stop_loss": 48000.0,
                "symbol": "BTCUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_loss_pips"] == 2000.0

    @pytest.mark.asyncio
    async def test_ethusd(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 3000.0,
                "stop_loss": 2850.0,
                "symbol": "ETHUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pip_value"] == 0.10

    @pytest.mark.asyncio
    async def test_unsupported_symbol(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 1.0850,
                "stop_loss": 1.0820,
                "symbol": "ZZZ999",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_zero_balance(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 0,
                "risk_percentage": 1.0,
                "entry_price": 1.0850,
                "stop_loss": 1.0820,
                "symbol": "EURUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 422  # validation error (gt=0)

    @pytest.mark.asyncio
    async def test_entry_equals_sl(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 1.0850,
                "stop_loss": 1.0850,
                "symbol": "EURUSD",
                "leverage": 100,
            },
            headers=headers,
        )
        assert response.status_code == 400  # zero SL distance

    @pytest.mark.asyncio
    async def test_unauthorized(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/risk/calculate",
            json={
                "account_balance": 10000.0,
                "risk_percentage": 1.0,
                "entry_price": 1.0850,
                "stop_loss": 1.0820,
                "symbol": "EURUSD",
                "leverage": 100,
            },
        )
        assert response.status_code == 401


# ── /pip-values ───────────────────────────────────────────────────────────────


class TestPipValues:
    @pytest.mark.asyncio
    async def test_all_symbols(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/risk/pip-values", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 10
        symbols = [s["symbol"] for s in data["symbols"]]
        assert "EURUSD" in symbols
        assert "BTCUSD" in symbols

        for s in data["symbols"]:
            assert "pip_size" in s
            assert "pip_value_per_lot" in s
            assert s["pip_value_per_lot"] > 0

    @pytest.mark.asyncio
    async def test_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/risk/pip-values")
        assert response.status_code == 401


# ── /limits ───────────────────────────────────────────────────────────────────


class TestRiskLimits:
    @pytest.mark.asyncio
    async def test_get_defaults(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/risk/limits", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user.id
        assert data["max_daily_loss"] is None
        assert data["max_weekly_loss"] is None
        assert data["current_daily_loss"] == 0.0
        assert data["current_weekly_loss"] == 0.0
        assert data["last_daily_reset"] is not None
        assert data["last_weekly_reset"] is not None

    @pytest.mark.asyncio
    async def test_update_limits(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.put(
            "/api/v1/risk/limits",
            json={
                "max_daily_loss": 500.0,
                "max_weekly_loss": 2000.0,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_daily_loss"] == 500.0
        assert data["max_weekly_loss"] == 2000.0

        # Verify persistence
        response2 = await client.get("/api/v1/risk/limits", headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["max_daily_loss"] == 500.0
        assert data2["max_weekly_loss"] == 2000.0

    @pytest.mark.asyncio
    async def test_update_pct_limits(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.put(
            "/api/v1/risk/limits",
            json={
                "max_daily_loss_pct": 5.0,
                "max_weekly_loss_pct": 10.0,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_daily_loss_pct"] == 5.0
        assert data["max_weekly_loss_pct"] == 10.0

    @pytest.mark.asyncio
    async def test_partial_update(self, client: AsyncClient, db_session):
        """Only provided fields change; others persist."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        # Set both
        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss": 500.0, "max_weekly_loss": 2000.0},
            headers=headers,
        )
        # Update only daily
        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss": 300.0},
            headers=headers,
        )

        response = await client.get("/api/v1/risk/limits", headers=headers)
        data = response.json()
        assert data["max_daily_loss"] == 300.0
        assert data["max_weekly_loss"] == 2000.0  # unchanged

    @pytest.mark.asyncio
    async def test_update_invalid_pct(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss_pct": 150.0},  # > 100
            headers=headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/risk/limits")
        assert response.status_code == 401

        response = await client.put("/api/v1/risk/limits", json={"max_daily_loss": 500.0})
        assert response.status_code == 401


# ── /status ───────────────────────────────────────────────────────────────────


class TestRiskStatus:
    @pytest.mark.asyncio
    async def test_default_allowed(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get("/api/v1/risk/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is True
        assert data["reason"] is None
        assert data["daily_loss"] == 0.0
        assert data["weekly_loss"] == 0.0

    @pytest.mark.asyncio
    async def test_blocked_when_limit_hit(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        # Set daily limit to $100
        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss": 100.0},
            headers=headers,
        )

        # Need to manually set the current_daily_loss — we use the service directly
        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 150.0)
        await db_session.commit()

        response = await client.get("/api/v1/risk/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is False
        assert data["daily_loss"] == 150.0
        assert "Daily loss limit reached" in (data["reason"] or "")

    @pytest.mark.asyncio
    async def test_not_blocked_below_limit(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss": 100.0},
            headers=headers,
        )

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 50.0)
        await db_session.commit()

        response = await client.get("/api/v1/risk/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is True
        assert data["daily_loss"] == 50.0

    @pytest.mark.asyncio
    async def test_weekly_limit(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        await client.put(
            "/api/v1/risk/limits",
            json={"max_weekly_loss": 500.0},
            headers=headers,
        )

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 600.0)
        await db_session.commit()

        response = await client.get("/api/v1/risk/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is False
        assert "Weekly loss limit reached" in (data["reason"] or "")

    @pytest.mark.asyncio
    async def test_status_with_balance_pct(self, client: AsyncClient, db_session):
        """Percentage-based limits checked with account_balance param."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss_pct": 5.0},
            headers=headers,
        )

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        # account_balance = 1000, 5% = $50 limit. Record $75 loss.
        await service.record_loss(str(user.id), 75.0)
        await db_session.commit()

        response = await client.get(
            "/api/v1/risk/status?account_balance=1000.0", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is False
        assert "Daily loss limit reached" in (data["reason"] or "")

    @pytest.mark.asyncio
    async def test_status_with_pct_not_breached(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        await client.put(
            "/api/v1/risk/limits",
            json={"max_daily_loss_pct": 5.0},
            headers=headers,
        )

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 20.0)
        await db_session.commit()

        response = await client.get(
            "/api/v1/risk/status?account_balance=1000.0", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trading_allowed"] is True  # 20 < 50

    @pytest.mark.asyncio
    async def test_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/risk/status")
        assert response.status_code == 401


# ── /reset ────────────────────────────────────────────────────────────────────


class TestRiskReset:
    @pytest.mark.asyncio
    async def test_reset_daily(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        # Record a loss
        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 200.0)
        await db_session.commit()

        # Verify loss is recorded
        resp1 = await client.get("/api/v1/risk/limits", headers=headers)
        assert resp1.json()["current_daily_loss"] == 200.0

        # Reset daily
        response = await client.post(
            "/api/v1/risk/reset?reset_daily=true&reset_weekly=false", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_daily_loss"] == 0.0

        # Verify reset persisted
        resp2 = await client.get("/api/v1/risk/limits", headers=headers)
        assert resp2.json()["current_daily_loss"] == 0.0
        assert resp2.json()["current_weekly_loss"] == 200.0  # weekly NOT reset

    @pytest.mark.asyncio
    async def test_reset_weekly(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 300.0)
        await db_session.commit()

        response = await client.post(
            "/api/v1/risk/reset?reset_daily=false&reset_weekly=true", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_weekly_loss"] == 0.0

    @pytest.mark.asyncio
    async def test_reset_both(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        from app.repositories.risk_repository import RiskSettingsRepository
        from app.services.risk_settings_service import RiskSettingsService

        service = RiskSettingsService(RiskSettingsRepository(db_session))
        await service.record_loss(str(user.id), 400.0)
        await db_session.commit()

        response = await client.post(
            "/api/v1/risk/reset?reset_daily=true&reset_weekly=true", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_daily_loss"] == 0.0
        assert data["current_weekly_loss"] == 0.0

    @pytest.mark.asyncio
    async def test_reset_neither_returns_current(self, client: AsyncClient, db_session):
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.post(
            "/api/v1/risk/reset?reset_daily=false&reset_weekly=false", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_daily_loss"] == 0.0
        assert data["current_weekly_loss"] == 0.0

    @pytest.mark.asyncio
    async def test_unauthorized(self, client: AsyncClient):
        response = await client.post("/api/v1/risk/reset")
        assert response.status_code == 401
