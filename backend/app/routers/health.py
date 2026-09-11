"""Health, readiness and internal metrics endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from app.services.health import (
    liveness_snapshot,
    readiness_snapshot,
)
from app.services.observability import metrics

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live():
    """Lightweight liveness probe. Always 200 while the process is up."""
    return liveness_snapshot()


@router.get("/health/ready")
async def health_ready():
    """Detailed readiness probe: API, PostgreSQL, Redis, market-data, feed."""
    report = await readiness_snapshot()
    # Hard-fail (503) only when a core dependency (app/DB/Redis) is down.  A
    # degraded optional market-data feed leaves the API available (HTTP 200).
    core = report["components"]
    core_ok = all(core[k]["status"] == "ok" for k in ("api", "database", "redis"))
    status_code = 200 if core_ok else 503
    return JSONResponse(content=report, status_code=status_code)


@router.get("/health/metrics")
async def health_metrics():
    """In-process metrics surface: counters and latency percentiles."""
    return JSONResponse(content=metrics.snapshot())


@router.get("/health/metrics/prometheus")
async def health_metrics_prometheus():
    """Prometheus-compatible text exposition of the in-process counters."""
    return PlainTextResponse(
        content=metrics.prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
