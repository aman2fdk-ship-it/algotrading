"""Health/readiness helpers for the ForexAI backend.

Liveness is intentionally trivial (the process is up).  Readiness performs
lightweight real connectivity checks against PostgreSQL, Redis and the
market-data provider and reports each component's status without ever including
secrets or credentials in the response.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.services.observability import metrics

logger = logging.getLogger(__name__)


def _fmt_latency(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def liveness_snapshot() -> dict[str, Any]:
    """Lightweight liveness payload. Always 200 while the process is up."""
    return {
        "status": "ok",
        "service": "forexai-terminal-backend",
        "version": "0.2.0",
    }


async def check_api() -> dict[str, Any]:
    """The API app itself is inherently up when this handler runs."""
    return {"status": "ok", "detail": "API app is up", "latency_ms": 0.0}


async def check_database(engine=None) -> dict[str, Any]:
    """Probe PostgreSQL via the app's async engine with a trivial SELECT 1.

    ``engine`` defaults to the app-wide engine from ``app.database`` so the
    check reflects real connectivity without leaking any DSN/credentials.
    """
    start = time.perf_counter()
    if engine is None:
        from app.database import engine
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            value = result.scalar()
        ok = value == 1
        return {
            "status": "ok" if ok else "degraded",
            "detail": "PostgreSQL reachable" if ok else "PostgreSQL returned unexpected result",
            "latency_ms": _fmt_latency(start),
        }
    except Exception as exc:  # noqa: BLE001 - surface any connectivity failure
        logger.warning("Database readiness check failed: %s", exc)
        return {
            "status": "down",
            "detail": f"PostgreSQL unreachable: {type(exc).__name__}",
            "latency_ms": _fmt_latency(start),
        }


async def check_redis(url: str | None = None) -> dict[str, Any]:
    """Probe Redis connectivity with an authenticated PING.

    ``url`` defaults to ``settings.REDIS_URL``.  Credentials/URLs are never
    returned to the caller of the readiness endpoint.
    """
    start = time.perf_counter()
    if url is None:
        from app.config import settings
        url = settings.REDIS_URL
    if not url:
        return {"status": "down", "detail": "Redis not configured", "latency_ms": _fmt_latency(start)}
    try:
        from urllib.parse import urlparse
        import redis.asyncio as aioredis
        parsed = urlparse(url)
        client = aioredis.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            db=int((parsed.path or "/0").lstrip("/") or 0),
            socket_timeout=2,
        )
        try:
            pong = await client.ping()
        finally:
            await client.aclose()
        ok = pong is True
        return {
            "status": "ok" if ok else "degraded",
            "detail": "Redis reachable" if ok else "Redis PING did not succeed",
            "latency_ms": _fmt_latency(start),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis readiness check failed: %s", exc)
        return {
            "status": "down",
            "detail": f"Redis unreachable: {type(exc).__name__}",
            "latency_ms": _fmt_latency(start),
        }


async def check_market_data(provider=None) -> dict[str, Any]:
    """Report market-data provider health without leaking connection details.

    The mock source always reports "ok".  Real sources (OANDA/MT5) report
    their actual connectivity status; only a safe status/message is returned,
    never credentials.
    """
    start = time.perf_counter()
    if provider is None:
        from app.services.market_data_provider import get_market_data_provider
        try:
            provider = get_market_data_provider()
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not resolve market-data provider: %s", exc)
            return {
                "status": "degraded",
                "detail": "Market-data provider unavailable",
                "latency_ms": _fmt_latency(start),
            }
    name = type(provider).__name__.lower()
    if name.startswith("mt5provider"):
        # The mock fallback rides inside MT5Provider; report it as mock/ok.
        try:
            client = provider.client
            if type(client).__name__.lower().startswith("mock"):
                metrics.touch_feed()
                return {
                    "status": "ok",
                    "detail": "Mock market-data source (no live feed configured)",
                    "latency_ms": _fmt_latency(start),
                }
        except Exception:  # noqa: BLE001
            pass
    try:
        connected = await provider.is_connected()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Market-data health probe failed: %s", exc)
        return {
            "status": "degraded",
            "detail": f"Market-data provider error: {type(exc).__name__}",
            "latency_ms": _fmt_latency(start),
        }
    if connected:
        metrics.touch_feed()
    return {
        "status": "ok" if connected else "degraded",
        "detail": (
            "Market-data provider connected"
            if connected
            else "Market-data provider not connected (optional; API remains up)"
        ),
        "latency_ms": _fmt_latency(start),
    }


def feed_status() -> dict[str, Any]:
    """Report last-known feed heartbeat / interruption state from metrics."""
    snap = metrics.snapshot()["feed"]
    status = "ok" if snap["ok"] else "degraded"
    return {
        "status": status,
        "detail": "Feed heartbeat healthy" if snap["ok"] else "Feed interrupted",
        "feed_interruptions": metrics.feed_interruptions,
        "feed_recoveries": metrics.feed_recoveries,
        "interrupted_at": snap["interrupted_at"],
        "recovered_at": snap["recovered_at"],
        "last_seen": snap["last_seen"],
    }


async def readiness_snapshot(provider=None, engine=None, redis_url: str | None = None) -> dict[str, Any]:
    """Assemble the full readiness report and overall status.

    The API is considered ready (HTTP 200) when the core dependencies — the API
    app itself, PostgreSQL and Redis — are up.  The optional market-data feed
    only degrades the reported status (never a hard failure) so the API stays
    available when a broker feed is the only problem.
    """
    api = await check_api()
    db = await check_database(engine)
    redis = await check_redis(redis_url)
    market = await check_market_data(provider)
    feed = feed_status()

    core_ok = api["status"] == "ok" and db["status"] == "ok" and redis["status"] == "ok"
    overall = "ok" if core_ok else "degraded"

    return {
        "status": overall,
        "service": "forexai-terminal-backend",
        "version": "0.2.0",
        "components": {
            "api": api,
            "database": db,
            "redis": redis,
            "market_data": market,
            "feed": feed,
        },
    }
