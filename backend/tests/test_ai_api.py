"""Integration tests for AI Decision Engine API endpoints.

Tests the 4 API endpoints with real SQLite database.
"""

import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.models.smc_structure import SMCStructure
from app.models.technical_indicator import TechnicalIndicator
from app.models.ai_recommendation import AIRecommendation
from app.services.mt5_client import SUPPORTED_SYMBOLS


# ── Test Data Helpers ───────────────────────────────────────────────────────────

def _seed_candle(db_session, symbol="EURUSD", timeframe="H1", **kw):
    """Seed a single candle."""
    defaults = dict(
        symbol=symbol, timeframe=timeframe,
        timestamp=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
        open=1.0840, high=1.0860, low=1.0830, close=1.0850, tick_volume=100,
    )
    defaults.update(kw)
    c = Candle(**defaults)
    db_session.add(c)
    return c


def _seed_indicator(db_session, symbol="EURUSD", timeframe="H1", **kw):
    """Seed a technical indicator row."""
    defaults = dict(
        symbol=symbol, timeframe=timeframe,
        timestamp=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
        ema_20=1.0850, ema_50=1.0800, ema_200=1.0700,
        supertrend_direction=1, supertrend_value=1.0780, adx=28.0,
        rsi=55.0, macd_line=0.0005, macd_signal=0.0003, macd_histogram=0.0002,
        stoch_k=60.0, stoch_d=55.0,
        atr=0.0015, bb_upper=1.0880, bb_middle=1.0830, bb_lower=1.0780,
        vwap=1.0820,
        support_levels=json.dumps([1.0750, 1.0700]),
        resistance_levels=json.dumps([1.0900, 1.0950]),
        swing_high=1.0920, swing_low=1.0730,
    )
    defaults.update(kw)
    ind = TechnicalIndicator(id=str(uuid.uuid4()), **defaults)
    db_session.add(ind)
    return ind


def _seed_smc(db_session, symbol="EURUSD", timeframe="H1", structure_type="bos", direction="bullish", **kw):
    """Seed an SMC structure."""
    defaults = dict(
        symbol=symbol, timeframe=timeframe,
        timestamp=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
        structure_type=structure_type, direction=direction,
        price_low=1.0720, price_high=1.0780, price_mid=1.0750,
        key_level=1.0750, confidence=0.8, details="Test",
    )
    defaults.update(kw)
    s = SMCStructure(id=str(uuid.uuid4()), **defaults)
    db_session.add(s)
    return s


def _seed_recommendation(db_session, symbol="EURUSD", **kw):
    """Seed an AI recommendation."""
    defaults = dict(
        symbol=symbol, decision="BUY", confidence=65.0,
        entry_price=1.0850, stop_loss=1.0800,
        take_profit_1=1.0925, take_profit_2=1.1000,
        risk_reward_ratio=1.5, trend="Bullish", market_bias="Buy",
        risk_level="Low", reasoning="Test reasoning",
        timeframe_scores=json.dumps({"H1": 0.35, "H4": 0.40, "D1": 0.45}),
    )
    defaults.update(kw)
    rec = AIRecommendation(id=str(uuid.uuid4()), **defaults)
    db_session.add(rec)
    return rec


# ═════════════════════════════════════════════════════════════════════════════════
# POST /api/v1/ai/analyze
# ═════════════════════════════════════════════════════════════════════════════════


class TestAnalyzeEndpoint:

    @pytest.mark.asyncio
    async def test_analyze_returns_decision(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """POST /api/v1/ai/analyze should return a complete decision."""
        # Seed data for all timeframes
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
            _seed_candle(db_session, "EURUSD", tf)
            _seed_indicator(db_session, "EURUSD", tf)
        await db_session.commit()

        response = await client.post(
            "/api/v1/ai/analyze",
            json={"symbol": "EURUSD"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["decision"] in ("BUY", "SELL", "WAIT")
        assert 0.0 <= data["confidence"] <= 100.0
        assert "reasoning" in data
        assert "timeframe_scores" in data
        assert "timeframe_details" in data
        assert data["trend"] in ("Bullish", "Bearish", "Ranging")
        assert data["market_bias"] in ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell")
        assert data["risk_level"] in ("Low", "Medium", "High")

    @pytest.mark.asyncio
    async def test_analyze_invalid_symbol(self, client: AsyncClient, auth_headers: dict):
        """Invalid symbol should return 404."""
        response = await client.post(
            "/api/v1/ai/analyze",
            json={"symbol": "INVALID"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_no_data_returns_wait(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """With no indicator/candle data, should return WAIT gracefully."""
        response = await client.post(
            "/api/v1/ai/analyze",
            json={"symbol": "EURUSD"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "WAIT"
        assert data["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_analyze_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        """Unauthenticated request should fail."""
        response = await client.post(
            "/api/v1/ai/analyze",
            json={"symbol": "EURUSD"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analyze_persists_recommendation(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """After analyze, recommendation should be retrievable."""
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
            _seed_candle(db_session, "EURUSD", tf)
            _seed_indicator(db_session, "EURUSD", tf)
        await db_session.commit()

        # Run analyze
        await client.post(
            "/api/v1/ai/analyze",
            json={"symbol": "EURUSD"},
            headers=auth_headers,
        )

        # Now retrieve recommendation
        response = await client.get(
            "/api/v1/ai/recommendation/EURUSD",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"


# ═════════════════════════════════════════════════════════════════════════════════
# POST /api/v1/ai/analyze-batch
# ═════════════════════════════════════════════════════════════════════════════════


class TestAnalyzeBatchEndpoint:

    @pytest.mark.asyncio
    async def test_analyze_batch(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """POST /api/v1/ai/analyze-batch should return results for multiple symbols."""
        for sym in ["EURUSD", "GBPUSD"]:
            for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
                _seed_candle(db_session, sym, tf)
                _seed_indicator(db_session, sym, tf)
        await db_session.commit()

        response = await client.post(
            "/api/v1/ai/analyze-batch",
            json={"symbols": ["EURUSD", "GBPUSD"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        symbols = {r["symbol"] for r in data}
        assert symbols == {"EURUSD", "GBPUSD"}

    @pytest.mark.asyncio
    async def test_analyze_batch_invalid_symbol(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """Invalid symbol in batch should return ERROR."""
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
            _seed_candle(db_session, "EURUSD", tf)
            _seed_indicator(db_session, "EURUSD", tf)
        await db_session.commit()

        response = await client.post(
            "/api/v1/ai/analyze-batch",
            json={"symbols": ["EURUSD", "INVALID"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        decisions = {r["symbol"]: r["decision"] for r in data}
        assert decisions.get("INVALID") == "ERROR"
        assert decisions["EURUSD"] != "ERROR"

    @pytest.mark.asyncio
    async def test_analyze_batch_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        """Batch endpoint requires authentication."""
        response = await client.post(
            "/api/v1/ai/analyze-batch",
            json={"symbols": ["EURUSD"]},
        )
        assert response.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════════
# GET /api/v1/ai/recommendation/{symbol}
# ═════════════════════════════════════════════════════════════════════════════════


class TestRecommendationEndpoint:

    @pytest.mark.asyncio
    async def test_get_recommendation(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """GET /api/v1/ai/recommendation/{symbol} returns stored recommendation."""
        rec = _seed_recommendation(db_session, "EURUSD")
        await db_session.commit()

        response = await client.get(
            "/api/v1/ai/recommendation/EURUSD",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["decision"] == "BUY"
        assert data["confidence"] == 65.0
        assert data["entry_price"] == 1.0850
        assert data["stop_loss"] == 1.0800
        assert "timeframe_scores" in data
        assert isinstance(data["timeframe_scores"], dict)

    @pytest.mark.asyncio
    async def test_get_recommendation_not_found(self, client: AsyncClient, auth_headers: dict):
        """No recommendation -> 404."""
        response = await client.get(
            "/api/v1/ai/recommendation/EURUSD",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recommendation_invalid_symbol(self, client: AsyncClient, auth_headers: dict):
        """Invalid symbol -> 404."""
        response = await client.get(
            "/api/v1/ai/recommendation/INVALID",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recommendation_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        response = await client.get("/api/v1/ai/recommendation/EURUSD")
        assert response.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════════
# GET /api/v1/ai/recommendations
# ═════════════════════════════════════════════════════════════════════════════════


class TestRecommendationsListEndpoint:

    @pytest.mark.asyncio
    async def test_get_recommendations(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """GET /api/v1/ai/recommendations returns recent recommendations."""
        _seed_recommendation(db_session, "EURUSD")
        _seed_recommendation(db_session, "GBPUSD", decision="SELL", confidence=70.0)
        await db_session.commit()

        response = await client.get(
            "/api/v1/ai/recommendations",
            headers=auth_headers,
            params={"limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert "count" in data
        assert data["count"] == 2
        symbols = {r["symbol"] for r in data["recommendations"]}
        assert symbols == {"EURUSD", "GBPUSD"}

    @pytest.mark.asyncio
    async def test_get_recommendations_filter_by_symbol(self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict):
        """Filter by symbol."""
        _seed_recommendation(db_session, "EURUSD")
        _seed_recommendation(db_session, "GBPUSD")
        await db_session.commit()

        response = await client.get(
            "/api/v1/ai/recommendations",
            headers=auth_headers,
            params={"symbol": "EURUSD", "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["recommendations"][0]["symbol"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_recommendations_empty(self, client: AsyncClient, auth_headers: dict):
        """No recommendations -> empty list."""
        response = await client.get(
            "/api/v1/ai/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["recommendations"] == []

    @pytest.mark.asyncio
    async def test_get_recommendations_invalid_symbol_filter(self, client: AsyncClient, auth_headers: dict):
        """Invalid symbol filter -> 404."""
        response = await client.get(
            "/api/v1/ai/recommendations",
            headers=auth_headers,
            params={"symbol": "INVALID"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recommendations_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/ai/recommendations")
        assert response.status_code == 401
