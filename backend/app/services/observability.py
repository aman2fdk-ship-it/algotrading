"""In-process observability: metrics counters, latency sampling and feed state.

This module is deliberately dependency-light and secret-free.  It keeps plain
Python counters/ring-buffer in memory so operators (and future monitoring) can
see request throughput, error rates, auth failure rates, feed interruption
history and API latency without standing up any heavyweight monitoring
infrastructure.  Nothing here reads or stores credentials.

The single ``metrics`` instance is shared process-wide (module singleton), which
is exactly what the readiness/metrics endpoints and the auth/reconnection
services all write into / read from.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import RLock
from typing import Any

# Cap the number of latency samples kept for average/percentile calculations so
# the structure stays bounded and does not grow without limit over a long run.
MAX_LATENCY_SAMPLES = 5000


def _p95(values: list[float]) -> float | None:
    """Return the 95th percentile of ``values``, or None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


class Metrics:
    """Process-local metrics/event store used by the observability surface."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.requests_total = 0
        self.api_errors_4xx = 0
        self.api_errors_5xx = 0
        self.auth_failures = 0
        self.feed_interruptions = 0
        self.feed_recoveries = 0
        self._latencies_ms: list[float] = []
        self.start_time: float = time.time()
        # Feed heartbeat / interruption state (used by the readiness endpoint).
        self.feed_ok = True
        self.feed_last_seen: float | None = None
        self.feed_interrupted_at: float | None = None
        self.feed_recovered_at: float | None = None

    # -- Request / error counting -------------------------------------------
    def record_request(self, latency_ms: float, status_code: int | None) -> None:
        with self._lock:
            self.requests_total += 1
            if status_code is not None:
                if status_code >= 500:
                    self.api_errors_5xx += 1
                elif status_code >= 400:
                    self.api_errors_4xx += 1
            self._latencies_ms.append(latency_ms)
            if len(self._latencies_ms) > MAX_LATENCY_SAMPLES:
                self._latencies_ms = self._latencies_ms[-MAX_LATENCY_SAMPLES:]

    def record_auth_failure(self) -> None:
        with self._lock:
            self.auth_failures += 1

    # -- Feed interruption / recovery ----------------------------------------
    def record_feed_interruption(self) -> None:
        with self._lock:
            self.feed_interruptions += 1
            self.feed_ok = False
            self.feed_interrupted_at = time.time()

    def record_feed_recovery(self) -> None:
        with self._lock:
            self.feed_ok = True
            self.feed_recovered_at = time.time()
            self.feed_recoveries += 1

    def touch_feed(self) -> None:
        with self._lock:
            self.feed_last_seen = time.time()

    # -- Serialization helpers ------------------------------------------------
    @property
    def avg_latency_ms(self) -> float | None:
        with self._lock:
            if not self._latencies_ms:
                return None
            return round(sum(self._latencies_ms) / len(self._latencies_ms), 3)

    @property
    def p95_latency_ms(self) -> float | None:
        with self._lock:
            p = _p95(self._latencies_ms)
            return None if p is None else round(p, 3)

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.start_time, 3)

    def _epoch_to_iso(self, value: float | None) -> str | None:
        if value is None:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "api_errors_4xx": self.api_errors_4xx,
                "api_errors_5xx": self.api_errors_5xx,
                "auth_failures": self.auth_failures,
                "feed_interruptions": self.feed_interruptions,
                "feed_recoveries": self.feed_recoveries,
                "latency": {
                    "avg_ms": self.avg_latency_ms,
                    "p95_ms": self.p95_latency_ms,
                    "samples": len(self._latencies_ms),
                },
                "uptime_seconds": self.uptime_seconds,
                "feed": {
                    "ok": self.feed_ok,
                    "last_seen": self._epoch_to_iso(self.feed_last_seen),
                    "interrupted_at": self._epoch_to_iso(self.feed_interrupted_at),
                    "recovered_at": self._epoch_to_iso(self.feed_recovered_at),
                },
            }

    def prometheus_text(self) -> str:
        """Serialize counters in the Prometheus text exposition format.

        Dependency-light: this is just plain text formatting of the in-process
        counters; no ``prometheus_client`` dependency is required.
        """
        snap = self.snapshot()
        lines = [
            "# HELP forexai_requests_total Total HTTP requests handled.",
            "# TYPE forexai_requests_total counter",
            f"forexai_requests_total {snap['requests_total']}",
            "# HELP forexai_api_errors_4xx Total 4xx HTTP responses.",
            "# TYPE forexai_api_errors_4xx counter",
            f"forexai_api_errors_4xx {snap['api_errors_4xx']}",
            "# HELP forexai_api_errors_5xx Total 5xx HTTP responses.",
            "# TYPE forexai_api_errors_5xx counter",
            f"forexai_api_errors_5xx {snap['api_errors_5xx']}",
            "# HELP forexai_auth_failures Total failed auth events.",
            "# TYPE forexai_auth_failures counter",
            f"forexai_auth_failures {snap['auth_failures']}",
            "# HELP forexai_feed_interruptions Total market-data feed interruptions.",
            "# TYPE forexai_feed_interruptions counter",
            f"forexai_feed_interruptions {snap['feed_interruptions']}",
            "# HELP forexai_http_latency_avg_ms Average HTTP latency (ms).",
            "# TYPE forexai_http_latency_avg_ms gauge",
            f"forexai_http_latency_avg_ms {snap['latency']['avg_ms'] or 0}",
            "# HELP forexai_http_latency_p95_ms 95th percentile HTTP latency (ms).",
            "# TYPE forexai_http_latency_p95_ms gauge",
            f"forexai_http_latency_p95_ms {snap['latency']['p95_ms'] or 0}",
        ]
        return "\n".join(lines) + "\n"


metrics = Metrics()


def reset_metrics() -> None:
    """Reset the shared metrics instance (used by tests to get a clean slate)."""
    global metrics
    metrics = Metrics()
