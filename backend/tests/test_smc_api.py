"""Integration tests for SMC API endpoints."""

import json
import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient

from app.models.user import User
from app.models.smc_structure import SMCStructure
from app.repositories.smc_repository import SMCRepository


async def _create_test_user(db_session) -> User:
    """Create a test user and return it."""
    from app.utils.security import hash_password

    user = User(
        id=str(uuid.uuid4()),
        email="test@example.com",
        hashed_password=hash_password("password123"),
        name="Test User",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_headers_for(user: User) -> dict:
    """Generate auth headers for a user."""
    from app.utils.security import create_access_token
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def make_smc_structure(
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    structure_type: str = "bos",
    direction: str = "bullish",
    ts_offset: int = 0,
) -> SMCStructure:
    """Create a test SMCStructure with sample values."""
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return SMCStructure(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(base.timestamp() + ts_offset * 3600, tz=timezone.utc),
        structure_type=structure_type,
        direction=direction,
        price_low=1.0790,
        price_high=1.0820,
        price_mid=1.0805,
        key_level=1.0810,
        confidence=0.75,
        details=json.dumps({"info": "test"}),
    )


class TestSMCAPI:
    """Tests for SMC API endpoints."""

    @pytest.mark.asyncio
    async def test_get_smc_empty(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol} returns empty list when no data."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/smc/EURUSD?timeframe=H1&limit=50",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "H1"
        assert data["count"] == 0
        assert data["structures"] == []

    @pytest.mark.asyncio
    async def test_get_smc_with_data(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol} returns SMC structures."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        for i in range(5):
            struct = make_smc_structure(ts_offset=i)
            await repo.upsert(struct)

        response = await client.get(
            "/api/v1/smc/EURUSD?timeframe=H1&limit=50",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["structures"]) == 5
        first = data["structures"][0]
        assert first["structure_type"] == "bos"
        assert first["direction"] == "bullish"
        assert first["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_get_smc_invalid_symbol(self, client: AsyncClient, db_session):
        """Invalid symbol returns 404."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/smc/INVALID?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_smc_invalid_timeframe(self, client: AsyncClient, db_session):
        """Invalid timeframe returns 400."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/smc/EURUSD?timeframe=INVALID",
            headers=headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_smc_requires_auth(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/smc/EURUSD?timeframe=H1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_smc_by_type(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol}/type/{type} filters correctly."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=0))
        await repo.upsert(make_smc_structure(structure_type="fvg", ts_offset=1))

        response = await client.get(
            "/api/v1/smc/EURUSD/type/bos?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["structures"][0]["structure_type"] == "bos"

    @pytest.mark.asyncio
    async def test_get_smc_by_invalid_type(self, client: AsyncClient, db_session):
        """Invalid structure_type returns 400."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/smc/EURUSD/type/invalid_type?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_order_blocks(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol}/order-blocks returns only order blocks."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(structure_type="order_block", direction="bullish", ts_offset=0))
        await repo.upsert(make_smc_structure(structure_type="order_block", direction="bearish", ts_offset=1))
        await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=2))

        response = await client.get(
            "/api/v1/smc/EURUSD/order-blocks?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["order_blocks"]) == 2
        for ob in data["order_blocks"]:
            assert ob["structure_type"] == "order_block"

    @pytest.mark.asyncio
    async def test_get_liquidity(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol}/liquidity returns only liquidity sweeps."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(structure_type="liquidity_sweep", direction="bullish", ts_offset=0))
        await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=1))

        response = await client.get(
            "/api/v1/smc/EURUSD/liquidity?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["liquidity_sweeps"][0]["structure_type"] == "liquidity_sweep"

    @pytest.mark.asyncio
    async def test_get_fvg(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol}/fvg returns only fair value gaps."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(structure_type="fvg", direction="bullish", ts_offset=0))
        await repo.upsert(make_smc_structure(structure_type="fvg", direction="bearish", ts_offset=1))

        response = await client.get(
            "/api/v1/smc/EURUSD/fvg?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["fair_value_gaps"]) == 2

    @pytest.mark.asyncio
    async def test_get_premium_discount(self, client: AsyncClient, db_session):
        """GET /api/v1/smc/{symbol}/premium-discount returns zone assessment."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        repo = SMCRepository(db_session)
        struct = SMCStructure(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            structure_type="premium_discount",
            direction="bearish",
            price_high=1.1100,
            price_low=1.0900,
            price_mid=1.1070,
            confidence=0.85,
            details=json.dumps({
                "zone_type": "premium",
                "position_pct": 0.85,
                "swing_high": 1.1100,
                "swing_low": 1.0900,
            }),
        )
        await repo.upsert(struct)

        response = await client.get(
            "/api/v1/smc/EURUSD/premium-discount?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["zone_type"] == "premium"
        assert data["swing_high"] == 1.1100
        assert data["swing_low"] == 1.0900
        assert data["position_pct"] == 0.85
        assert data["current_price"] == 1.1070

    @pytest.mark.asyncio
    async def test_get_premium_discount_not_found(self, client: AsyncClient, db_session):
        """Premium/discount endpoint returns 404 when no data exists."""
        user = await _create_test_user(db_session)
        headers = _auth_headers_for(user)

        response = await client.get(
            "/api/v1/smc/EURUSD/premium-discount?timeframe=H1",
            headers=headers,
        )
        assert response.status_code == 404


class TestSMCRepository:
    """Tests for SMCRepository operations."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_all(self, db_session):
        """Test basic upsert and retrieval."""
        repo = SMCRepository(db_session)
        struct = make_smc_structure()
        await repo.upsert(struct)

        results = await repo.get_all("EURUSD", "H1", limit=10)
        assert len(results) == 1
        assert results[0].symbol == "EURUSD"
        assert results[0].confidence == 0.75

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db_session):
        """Test that upsert updates an existing row (same dedup key)."""
        repo = SMCRepository(db_session)
        struct1 = make_smc_structure(ts_offset=0)
        await repo.upsert(struct1)

        # Same key, different confidence
        struct2 = make_smc_structure(ts_offset=0)
        struct2.confidence = 0.90
        await repo.upsert(struct2)

        results = await repo.get_all("EURUSD", "H1", limit=10)
        assert len(results) == 1
        assert results[0].confidence == 0.90

    @pytest.mark.asyncio
    async def test_exists(self, db_session):
        """Test exists check."""
        repo = SMCRepository(db_session)
        struct = make_smc_structure()
        await repo.upsert(struct)

        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert await repo.exists("EURUSD", "H1", base, "bos", "bullish") is True
        assert await repo.exists("EURUSD", "H1", base, "fvg", "bullish") is False

    @pytest.mark.asyncio
    async def test_get_by_type(self, db_session):
        """Test filtering by structure_type."""
        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=0))
        await repo.upsert(make_smc_structure(structure_type="fvg", ts_offset=1))
        await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=2))

        bos_results = await repo.get_by_type("EURUSD", "H1", "bos", limit=10)
        assert len(bos_results) == 2
        assert all(r.structure_type == "bos" for r in bos_results)

        fvg_results = await repo.get_by_type("EURUSD", "H1", "fvg", limit=10)
        assert len(fvg_results) == 1

    @pytest.mark.asyncio
    async def test_get_latest(self, db_session):
        """Test get_latest returns the most recent structure of a type."""
        repo = SMCRepository(db_session)
        for i in range(3):
            await repo.upsert(make_smc_structure(structure_type="bos", ts_offset=i))

        latest = await repo.get_latest("EURUSD", "H1", "bos")
        assert latest is not None
        expected_ts = make_smc_structure(ts_offset=2).timestamp
        assert latest.timestamp.replace(tzinfo=None) == expected_ts.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_different_direction_separate_rows(self, db_session):
        """Same symbol/timeframe/timestamp/type but different direction = separate rows."""
        repo = SMCRepository(db_session)
        await repo.upsert(make_smc_structure(direction="bullish", ts_offset=0))
        await repo.upsert(make_smc_structure(direction="bearish", ts_offset=0))

        results = await repo.get_all("EURUSD", "H1", limit=10)
        assert len(results) == 2
        directions = {r.direction for r in results}
        assert directions == {"bullish", "bearish"}
