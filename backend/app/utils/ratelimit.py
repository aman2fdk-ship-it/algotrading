"""Dependency-light, in-memory rate limiting for authentication endpoints.

Mitigates credential-stuffing / brute-force on register/login/refresh by
throttling per-IP and per-account (email) using sliding-window counters.

Design notes
------------
- Pure-Python sliding-window limiter. No external packages, no Redis
  round-trips, so it "just works" in unit tests and has no network coupling.
- State is per-process (a module-level registry). For a single-Worker
  deployment this is sufficient; for multi-Worker production the limiter
  should be swapped for a shared backend (Redis) — the ``allow(key)``
  interface is the seam for that swap.
- Tests reset the registry between tests (see ``reset_rate_limiters`` and the
  autouse fixture in tests/conftest.py), so shared state never leaks across
  test cases.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from app.config import settings


class RateLimiter:
    """Sliding-window limiter: at most ``limit`` calls per ``window_seconds``.

    ``window_seconds`` of 0 disables limiting entirely (allows everything) —
    useful to degrade gracefully in tests or ops when throttling is unwanted.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 0:
            raise ValueError("rate limit must be >= 0")
        self.limit = limit
        self.window_seconds = float(window_seconds)
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @property
    def disabled(self) -> bool:
        return self.window_seconds <= 0 or self.limit <= 0

    def allow(self, key: str) -> bool:
        """Record a call for ``key`` and return True if it is within the limit.

        False means the key has exceeded the limit (caller should 429). A
        global request counter keeps this accurate even for unlimited modes.
        """
        if self.disabled:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, [])
            # Prune entries older than the window.
            cutoff = now - self.window_seconds
            hits[:] = [t for t in hits if t > cutoff]
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def remaining(self, key: str) -> int:
        """How many more calls ``key`` may make within the current window."""
        if self.disabled:
            return self.limit
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key, [])
            cutoff = now - self.window_seconds
            within = [t for t in hits if t > cutoff]
            return max(0, self.limit - len(within))

    def reset(self) -> None:
        """Clear all recorded hits for every key."""
        with self._lock:
            self._hits.clear()


def build_login_limiter() -> RateLimiter:
    return RateLimiter(
        settings.AUTH_LOGIN_RATE_LIMIT,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )


def build_register_limiter() -> RateLimiter:
    return RateLimiter(
        settings.AUTH_REGISTER_RATE_LIMIT,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )


def build_refresh_limiter() -> RateLimiter:
    return RateLimiter(
        settings.AUTH_REFRESH_RATE_LIMIT,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )


# Module-level singletons bound at import time. The auth routes reference these
# via helper getters so tests can monkeypatch them (see reset_rate_limiters).
login_limiter = build_login_limiter()
register_limiter = build_register_limiter()
refresh_limiter = build_refresh_limiter()

_LIMITER_GETTERS: dict[str, Callable[[], RateLimiter]] = {
    "login": lambda: login_limiter,
    "register": lambda: register_limiter,
    "refresh": lambda: refresh_limiter,
}


def reset_rate_limiters() -> None:
    """Clear recorded hits on all module-level limiters (used by tests)."""
    for limiter in (login_limiter, register_limiter, refresh_limiter):
        limiter.reset()


def ip_key(request) -> str:
    """Return a stable per-IP rate-limit key for a Starlette/FastAPI Request."""
    if request is not None and request.client is not None and request.client.host:
        return request.client.host
    return "unknown-ip"
