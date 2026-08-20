"""Runtime Redis cache service.

A thin async wrapper around redis.asyncio that is intentionally safe offline:

* When Redis is not configured (no ``REDIS_URL``) the cache is a no-op.
* When Redis is unreachable / down the cache logs a warning and *falls back*
  to ``None`` (for reads) or a no-op (for writes) instead of raising — so a
  Redis outage can never crash an API request.
* It is injected into services (Dependency Injection) so callers can also
  substitute an in-memory fake in tests.

Only the highest-value, short-TTL results are stored (e.g. the AI decision
engine output). The cache uses JSON with short TTLs (default 30s).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Sentinel used to detect a transient Redis failure without swallowing a
# legitimate cache miss (Redis returns None for a miss).
_MISS = object()


class RedisCache:
    """Async JSON cache with graceful degradation when Redis is down/disabled."""

    def __init__(
        self,
        url: Optional[str] = None,
        enabled: bool = True,
        default_ttl: int = 30,
        prefix: str = "fxai",
    ) -> None:
        self._url = url if url is not None else settings.REDIS_URL
        self._enabled = enabled
        self._default_ttl = default_ttl
        self._prefix = prefix
        self._client: Any = None
        self._client_factory: Callable[[], Awaitable[Any]] | None = None

    # ── Client lifecycle ──────────────────────────────────────────────────

    def _get_client(self) -> Any | None:
        """Return a lazily-created Redis client, or None when disabled.

        Does not raise: if Redis is not configured or the client cannot be
        built, we return None and every operation degrades to a no-op miss.
        """
        if not self._enabled or not self._url:
            return None
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Redis cache client init failed (fallback): %s", e)
            return None
        return self._client

    async def _close(self) -> None:
        """Drop a client that has gone into a bad state so we can retry fresh."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ── Low-level primitives (never raise) ────────────────────────────────

    async def _execute(self, op: str, *args: Any, **kwargs: Any) -> Any:
        """Run ``client.<op>(*args, **kwargs)``, returning _MISS on failure."""
        client = self._get_client()
        if client is None:
            return _MISS
        try:
            method = getattr(client, op)
            return await method(*args, **kwargs)
        except Exception as e:
            logger.warning("Redis %s failed (graceful fallback): %s", op, e)
            await self._close()
            return _MISS

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    # ── Public API ────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[str]:
        """Return the raw string cached at ``key``, or None on miss/failure."""
        raw = await self._execute("get", self._key(key))
        return None if raw is _MISS else raw

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store ``value`` at ``key`` with an expiry (default TTL when omitted)."""
        await self._execute("set", self._key(key), value, ex=ttl or self._default_ttl)

    async def delete(self, key: str) -> None:
        await self._execute("delete", self._key(key))

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):  # pragma: no cover - defensive
            logger.warning("Redis cache value at %r is not valid JSON; ignoring.", key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.set(key, json.dumps(value, default=str), ttl=ttl)

    async def close(self) -> None:
        await self._close()


# Module-level singleton shared across routers/services. Lazy client creation
# means constructing this is cheap even when REDIS_URL is unset.
redis_cache = RedisCache()
