"""End-to-end API contract tests for the ForexAI Terminal backend.

Verifies the critical API flows work through the full HTTP layer
(async test client + real SQLite test DB): health, symbols, AI analysis,
recommendations, risk calculation, backtest runs, indicators, and
auth enforcement on protected endpoints.

Uses the shared `client`, `db_session` and `auth_headers` fixtures from
conftest.py — no mocks of the application layer.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_recommendation import AIRecommendation
from app.models.backtest import BacktestRun
from app.models.candle import Candle
from app.models.symbol import Symbol
from app.models.technical_indicator import TechnicalIndicator
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES
from app.utils.security import decode_token


# ── Test data helpers ──────────────────────────────────────────────────────────


def _seed_symbols(db_session: AsyncSession) -> None:
    """Seed the 10 supported symbols (mirrors main.py _seed_symbols)."""
    for code in SUPPORTED_SYMBOLS:
        db_session.add(
            Symbol(code=code, name=code, asset_type="forex", pip_size=0.0001, digits=5, enabled=True)
        )


def _seed_candle(db_session: AsyncSession, symbol: str = "EURUSD", timeframe: str = "H1") -> None:
    db_session.add(
        Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
            open=1.0840,
            high=1.0860,
            low=1.0830,
            close=1.0850,
            tick_volume=100,
        )
    )


def _seed_indicator(db_session: AsyncSession, symbol: str = "EURUSD", timeframe: str = "H1") -> None:
    db_session.add(
        TechnicalIndicator(
            id=str(uuid.uuid4()),
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
            ema_20=1.0850,
            ema_50=1.0800,
            ema_200=1.0700,
            supertrend_direction=1,
            supertrend_value=1.0780,
            adx=28.0,
            rsi=55.0,
            macd_line=0.0005,
            macd_signal=0.0003,
            macd_histogram=0.0002,
            stoch_k=60.0,
            stoch_d=55.0,
            atr=0.0015,
            bb_upper=1.0880,
            bb_middle=1.0830,
            bb_lower=1.0780,
            vwap=1.0820,
            support_levels=[1.0750, 1.0700],
            resistance_levels=[1.0900, 1.0950],
            swing_high=1.0920,
            swing_low=1.0730,
        )
    )


def _seed_full_analysis_data(db_session: AsyncSession, symbol: str = "EURUSD") -> None:
    """Seed candles + indicators for every supported timeframe."""
    for tf in SUPPORTED_TIMEFRAMES:
        _seed_candle(db_session, symbol, tf)
        _seed_indicator(db_session, symbol, tf)


def _seed_recommendation(
    db_session: AsyncSession,
    symbol: str = "EURUSD",
    decision: str = "BUY",
    confidence: float = 65.0,
) -> None:
    db_session.add(
        AIRecommendation(
            id=str(uuid.uuid4()),
            symbol=symbol,
            decision=decision,
            confidence=confidence,
            entry_price=1.0850,
            stop_loss=1.0800,
            take_profit_1=1.0925,
            take_profit_2=1.1000,
            risk_reward_ratio=1.5,
            trend="Bullish",
            market_bias="Buy",
            risk_level="Low",
            reasoning="Test reasoning",
            timeframe_scores=json.dumps({"H1": 0.35, "H4": 0.40, "D1": 0.45}),
        )
    )


def _seed_backtest_run(db_session: AsyncSession, user_id: str, symbol: str = "EURUSD") -> None:
    db_session.add(
        BacktestRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            symbol=symbol,
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


def _user_id_from_headers(auth_headers: dict) -> str:
    """Extract the user id encoded in the auth_headers access token."""
    token = auth_headers["Authorization"].replace("Bearer ", "")
    return decode_token(token)["sub"]


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health_check_returns_200(client: AsyncClient):
    """GET /health is public and returns service status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Symbols
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_symbols_returns_expected_symbols(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """GET /api/v1/symbols returns all supported symbols with metadata."""
    _seed_symbols(db_session)
    await db_session.commit()

    response = await client.get("/api/v1/symbols", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(SUPPORTED_SYMBOLS)
    codes = {s["code"] for s in data["symbols"]}
    assert codes == set(SUPPORTED_SYMBOLS)
    # Spot-check metadata shape
    eurusd = next(s for s in data["symbols"] if s["code"] == "EURUSD")
    assert eurusd["pip_size"] == 0.0001
    assert eurusd["enabled"] is True


@pytest.mark.asyncio
async def test_symbols_requires_authentication(client: AsyncClient):
    """GET /api/v1/symbols without a token is rejected."""
    response = await client.get("/api/v1/symbols")
    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# AI Decision Engine
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ai_analyze_valid_payload_returns_decision(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """POST /api/v1/ai/analyze returns BUY/SELL/WAIT with a 0-100 confidence."""
    _seed_full_analysis_data(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/ai/analyze", json={"symbol": "EURUSD"}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "EURUSD"
    assert data["decision"] in ("BUY", "SELL", "WAIT")
    assert 0.0 <= data["confidence"] <= 100.0
    assert "reasoning" in data
    assert "timeframe_scores" in data
    assert "timeframe_details" in data


@pytest.mark.asyncio
async def test_ai_analyze_no_data_returns_wait(
    client: AsyncClient, auth_headers: dict
):
    """Without market data the engine degrades to a WAIT decision."""
    response = await client.post(
        "/api/v1/ai/analyze", json={"symbol": "EURUSD"}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "WAIT"
    assert data["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ai_analyze_unknown_symbol_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """Analyzing an unsupported symbol returns 404."""
    response = await client.post(
        "/api/v1/ai/analyze", json={"symbol": "UNKNOWN"}, headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ai_analyze_requires_authentication(client: AsyncClient):
    """POST /api/v1/ai/analyze without a token is rejected."""
    response = await client.post("/api/v1/ai/analyze", json={"symbol": "EURUSD"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ai_recommendations_returns_list(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """GET /api/v1/ai/recommendations returns persisted recommendations."""
    _seed_recommendation(db_session, "EURUSD")
    _seed_recommendation(db_session, "GBPUSD", decision="SELL", confidence=70.0)
    await db_session.commit()

    response = await client.get("/api/v1/ai/recommendations", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["recommendations"]) == 2
    rec = data["recommendations"][0]
    assert rec["id"]
    assert rec["symbol"] in ("EURUSD", "GBPUSD")
    assert rec["decision"] in ("BUY", "SELL", "WAIT")
    assert 0.0 <= rec["confidence"] <= 100.0


@pytest.mark.asyncio
async def test_ai_recommendations_empty_returns_empty_list(
    client: AsyncClient, auth_headers: dict
):
    """With no recommendations the endpoint returns an empty list."""
    response = await client.get("/api/v1/ai/recommendations", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["recommendations"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Management
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_risk_calculate_returns_position_sizing(
    client: AsyncClient, auth_headers: dict
):
    """POST /api/v1/risk/calculate returns position size, lots and margin."""
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
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "EURUSD"
    assert data["position_size"] > 0
    assert data["lot_size"] > 0
    assert data["required_margin"] > 0
    assert data["risk_amount"] == pytest.approx(100.0)  # 1% of 10,000
    assert data["stop_loss_pips"] == pytest.approx(30.0)
    assert data["pip_value"] > 0


@pytest.mark.asyncio
async def test_risk_calculate_unknown_symbol_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """Risk calculation for an unsupported symbol returns 404."""
    response = await client.post(
        "/api/v1/risk/calculate",
        json={
            "account_balance": 10000.0,
            "risk_percentage": 1.0,
            "entry_price": 1.0850,
            "stop_loss": 1.0820,
            "symbol": "UNKNOWN",
            "leverage": 100,
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_risk_calculate_requires_authentication(client: AsyncClient):
    """POST /api/v1/risk/calculate without a token is rejected."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# Backtesting
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_backtest_runs_returns_paginated_list(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """GET /api/v1/backtest/runs returns paginated runs for the current user."""
    user_id = _user_id_from_headers(auth_headers)
    _seed_backtest_run(db_session, user_id, "EURUSD")
    _seed_backtest_run(db_session, user_id, "GBPUSD")
    _seed_backtest_run(db_session, user_id, "USDJPY")
    await db_session.commit()

    response = await client.get(
        "/api/v1/backtest/runs", params={"limit": 2, "offset": 0}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["runs"]) == 2
    run = data["runs"][0]
    assert run["id"]
    assert run["user_id"] == user_id
    assert "trades" not in run  # summaries only

    # Second page returns the remaining run
    response2 = await client.get(
        "/api/v1/backtest/runs", params={"limit": 2, "offset": 2}, headers=auth_headers
    )
    data2 = response2.json()
    assert data2["count"] == 1
    assert len(data2["runs"]) == 1


@pytest.mark.asyncio
async def test_backtest_runs_empty_returns_empty_list(
    client: AsyncClient, auth_headers: dict
):
    """With no runs the endpoint returns an empty list."""
    response = await client.get("/api/v1/backtest/runs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["runs"] == []


@pytest.mark.asyncio
async def test_backtest_runs_requires_authentication(client: AsyncClient):
    """GET /api/v1/backtest/runs without a token is rejected."""
    response = await client.get("/api/v1/backtest/runs")
    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Technical Indicators
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_indicators_latest_returns_indicator_data(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """GET /api/v1/indicators/{symbol}/latest returns the latest snapshot."""
    _seed_indicator(db_session, "EURUSD", "H1")
    await db_session.commit()

    response = await client.get(
        "/api/v1/indicators/EURUSD/latest?timeframe=H1", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    ind = data["indicator"]
    assert ind["symbol"] == "EURUSD"
    assert ind["timeframe"] == "H1"
    assert ind["ema_20"] == pytest.approx(1.0850)
    assert ind["rsi"] == pytest.approx(55.0)
    assert ind["support_levels"] == [1.0750, 1.0700]
    assert ind["resistance_levels"] == [1.0900, 1.0950]


@pytest.mark.asyncio
async def test_indicators_latest_no_data_returns_empty_indicator(
    client: AsyncClient, auth_headers: dict
):
    """Supported symbol with no indicator data returns 200 with a null indicator."""
    response = await client.get(
        "/api/v1/indicators/EURUSD/latest?timeframe=H1", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["indicator"] is None


@pytest.mark.asyncio
async def test_indicators_unknown_symbol_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """Unsupported symbol returns 404 before any data lookup."""
    response = await client.get(
        "/api/v1/indicators/UNKNOWN/latest", headers=auth_headers
    )
    assert response.status_code == 404
