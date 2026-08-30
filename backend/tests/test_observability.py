"""Observability tests: health/readiness endpoints, metrics counters and secrets safety.

Coverage:
1. Liveness        - GET /health/live answers 200 quickly; legacy /health stays "healthy".
2. Readiness       - reflects real PostgreSQL + Redis (ok when up); degrades when a
                     component is down, then restores when services come back.
3. Metrics         - counters increment on auth failures and 4xx/5xx; latency is
                     recorded and surfaced on /health/metrics and the Prometheus text
                     endpoint.
4. Secrets safety  - the readiness payload never contains configured secrets
                     (OANDA_API_KEY / OANDA_ACCOUNT_ID / JWT secret / DB and Redis
                     passwords).

Deterministic HTTP tests use the SQLite ``client`` fixture (consistent with
test_security.py).  The real PG+Redis readiness assertions are gated on the
``redis_client`` fixture so they run against the live services in the integration
run and skip gracefully when Redis is unavailable.
"""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.health import readiness_snapshot
from app.services.observability import Metrics

# A stable origin in the default CORS allow-list (see app/config.py).
ALLOWED_ORIGIN = "http://localhost:3000"


# ── Unit tests: Metrics in isolation ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_metrics_record_request_counts_errors_and_5xx():
    m = Metrics()
    m.record_request(1.0, 200)
    m.record_request(2.0, 404)
    m.record_request(3.0, 500)
    snap = m.snapshot()
    assert snap["requests_total"] == 3
    assert snap["api_errors_4xx"] == 1
    assert snap["api_errors_5xx"] == 1
    assert snap["latency"]["samples"] == 3
    assert snap["latency"]["avg_ms"] is not None
    assert snap["latency"]["p95_ms"] is not None


@pytest.mark.asyncio
async def test_metrics_feed_interruption_recovery():
    m = Metrics()
    assert m.snapshot()["feed"]["ok"] is True
    m.record_feed_interruption()
    s = m.snapshot()
    assert s["feed_interruptions"] == 1
    assert s["feed"]["ok"] is False
    m.record_feed_recovery()
    s2 = m.snapshot()
    assert s2["feed_recoveries"] == 1
    assert s2["feed"]["ok"] is True


@pytest.mark.asyncio
async def test_metrics_prometheus_text():
    m = Metrics()
    m.record_request(2.0, 200)
    body = m.prometheus_text()
    assert "forexai_requests_total 1" in body
    assert "forexai_auth_failures" in body
    assert "forexai_http_latency_avg_ms" in body


# ── Liveness ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_live_returns_200_quickly(client):
    import time

    start = time.perf_counter()
    resp = await client.get("/health/live")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    # Liveness must be near-instant; anything over 2s is suspicious.
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_legacy_health_alias_stays_healthy(client):
    # Pre-observability contract (test_e2e_api asserts status == "healthy").
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


# ── Metrics counters / latency over the HTTP surface ────────────────────────────
@pytest.mark.asyncio
async def test_metrics_counters_increment_and_latency_recorded(client):
    from app.services.observability import metrics

    base = metrics.snapshot()

    # A 4xx (404) — should bump api_errors_4xx via the request middleware.
    r = await client.get("/definitely/not/a/route/xyz")
    assert r.status_code == 404

    # A failed auth (bad login) — should bump auth_failures *and* a 4xx.
    r = await client.post(
        "/auth/login",
        json={"email": "missing-user@example.com", "password": "WrongPass1!"},
    )
    assert r.status_code == 401

    now = metrics.snapshot()
    assert now["requests_total"] >= base["requests_total"] + 2
    assert now["api_errors_4xx"] >= base["api_errors_4xx"] + 2  # 404 + 401
    assert now["auth_failures"] >= base["auth_failures"] + 1
    assert now["latency"]["samples"] >= base["latency"]["samples"] + 2
    assert now["latency"]["avg_ms"] is not None


@pytest.mark.asyncio
async def test_metrics_endpoints_expose_counters(client):
    from app.services.observability import metrics

    await client.get("/health/live")
    # JSON surface
    resp = await client.get("/health/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "requests_total" in data
    assert "latency" in data and "avg_ms" in data["latency"]
    # Prometheus text surface
    prom = await client.get("/health/metrics/prometheus")
    assert prom.status_code == 200
    assert "forexai_requests_total" in prom.text
    assert metrics.requests_total > 0


# ── Secrets safety (deterministic: controlled engine + dead redis) ─────────────
@pytest.mark.asyncio
async def test_readiness_output_contains_no_secrets(client):
    from urllib.parse import urlparse

    from app.config import settings

    # Deterministic and fast: a local SQLite engine (instant SELECT 1) and a
    # dead Redis port keep this independent of external service availability.
    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    report = await readiness_snapshot(engine=engine, redis_url="redis://127.0.0.1:1/0")
    await engine.dispose()

    text_repr = json.dumps(report)

    configured: list[str] = []
    for v in (
        settings.OANDA_API_KEY,
        settings.OANDA_ACCOUNT_ID,
        settings.MT5_PASSWORD,
        settings.JWT_SECRET,
    ):
        if v:
            configured.append(str(v))
    for url in (settings.DATABASE_URL,):
        p = urlparse(url.replace("+asyncpg", ""))
        if p.password:
            configured.append(p.password)
    p = urlparse(settings.REDIS_URL)
    if p.password:
        configured.append(p.password)

    lowered = text_repr.lower()
    for secret in configured:
        # Skip the dev placeholder so we still catch real secret leaks.
        if "dev-secret-key" in secret:
            continue
        assert secret.lower() not in lowered, f"secret leaked into readiness: {secret}"


# ── Readiness integration (real PostgreSQL + Redis) ─────────────────────────────
@pytest.mark.postgres
@pytest.mark.redis
@pytest.mark.asyncio
async def test_readiness_ready_when_services_up(client, redis_client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["components"]["database"]["status"] == "ok"
    assert data["components"]["redis"]["status"] == "ok"


@pytest.mark.postgres
@pytest.mark.redis
@pytest.mark.asyncio
async def test_readiness_degrades_then_restores(redis_client):
    # 1) Destroy a component (dead engine + dead redis) -> readiness reflects down.
    dead_engine = create_async_engine(
        "postgresql+asyncpg://u:p@127.0.0.1:59999/nope",
        connect_args={"timeout": 1},
        poolclass=NullPool,
    )
    degraded = await readiness_snapshot(
        engine=dead_engine,
        redis_url="redis://127.0.0.1:59998/0",
    )
    await dead_engine.dispose()
    assert degraded["components"]["database"]["status"] == "down"
    assert degraded["components"]["redis"]["status"] == "down"
    assert degraded["status"] == "degraded"

    # 2) Back to real services -> readiness restores to ok.  A fresh engine is
    # used here (rather than the module-level app engine) because that shared
    # engine gets bound to an earlier test's function-scoped event loop under
    # pytest-asyncio strict mode; reusing it on this loop would fail with
    # "Future attached to a different loop" and falsely report "down".
    from app.config import settings

    restore_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    restored = await readiness_snapshot(
        engine=restore_engine,
        redis_url=settings.REDIS_URL,
    )
    await restore_engine.dispose()
    assert restored["components"]["database"]["status"] == "ok"
    assert restored["components"]["redis"]["status"] == "ok"
    assert restored["status"] == "ok"
