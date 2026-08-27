"""Security hardening tests.

Covers the five hardening areas introduced in the security-hardening branch:

1. JWT / production-startup guard   - app refuses to start with missing/empty/
   placeholder/too-short JWT_SECRET when APP_ENV is production, but dev mode
   defaults without failing.
2. CORS allow-list                  - disallowed origins rejected, allowed
   origins accepted, and wildcard is never combined with credentials.
3. Rate limiting                    - exceeding the per-window auth limit yields
   429; normal traffic passes.
4. Endpoint authorization           - every protected endpoint returns 401
   without a token; public endpoints remain reachable anonymously.
5. Secrets safety                   - broker credentials never leak into API
   payloads and are never persisted to the database.

Deterministic: rate-limiter buckets are reset between tests by the autouse
``_reset_auth_rate_limiters`` fixture in tests/conftest.py. Tests in this file
that need a non-default limit monkeypatch the module-level limiter directly and
rely on that fixture (plus monkeypatch teardown) to keep state clean.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import (
    PLACEHOLDER_JWT_SECRET,
    MIN_PRODUCTION_SECRET_LENGTH,
    Settings,
    settings,
)
from app.utils.ratelimit import login_limiter

# A stable origin that IS in the default CORS allow-list (see app/config.py).
ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "https://evil.example.com"


# ── 1. JWT / production startup guard ─────────────────────────────────────────
def _prod_settings(**overrides) -> Settings:
    """Build a production Settings with CORS normalized for deterministic tests.

    A valid secret is injected by default so tests that focus on CORS or auth
    reach their own guards. Passing ``JWT_SECRET=None`` explicitly means "secret
    not provided at all" -- the helper then omits it entirely so Settings falls
    back to its dev placeholder and the production guard fires.
    """
    inject_secret = True
    if "JWT_SECRET" in overrides and overrides["JWT_SECRET"] is None:
        inject_secret = False
        del overrides["JWT_SECRET"]
    defaults = {
        "APP_ENV": "production",
        "CORS_ORIGINS": '["https://app.example.com"]',
    }
    if inject_secret:
        defaults["JWT_SECRET"] = "x" * 64
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.parametrize(
    "secret",
    [
        "",  # missing / empty
        None,  # not provided
        PLACEHOLDER_JWT_SECRET,  # dev placeholder
        "short",  # below MIN_PRODUCTION_SECRET_LENGTH
    ],
)
def test_production_requires_real_jwt_secret(secret):
    # Pass JWT_SECRET explicitly in every case: None is treated by the helper as
    # "not provided at all" (falls back to the dev placeholder), not as a value.
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _prod_settings(JWT_SECRET=secret)


def test_production_accepts_long_random_secret():
    settings_obj = _prod_settings(JWT_SECRET="Z" * MIN_PRODUCTION_SECRET_LENGTH)
    assert settings_obj.JWT_SECRET == "Z" * MIN_PRODUCTION_SECRET_LENGTH


def test_dev_mode_defaults_without_failing():
    """Dev mode must not fail on a weak/missing secret."""
    dev = Settings(APP_ENV="development", CORS_ORIGINS='["http://localhost:3000"]')
    assert dev.JWT_SECRET  # placeholder present, but allowed in dev


def test_production_rejects_wildcard_cors_with_credentials():
    with pytest.raises(ValueError, match="[Ww]ildcard"):
        _prod_settings(CORS_ORIGINS='["*"]')


def test_production_rejects_empty_cors_origins():
    with pytest.raises(ValueError, match="non-empty JSON list"):
        _prod_settings(CORS_ORIGINS="[]")


# ── 2. CORS allow-list enforcement ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cors_disallowed_origin_rejected(client: AsyncClient):
    resp = await client.get("/health", headers={"Origin": DISALLOWED_ORIGIN})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.asyncio
async def test_cors_allowed_origin_accepted(client: AsyncClient):
    resp = await client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_cors_config_never_allows_wildcard_with_credentials():
    """Config validation guarantees the middleware can never see a '*' origin."""
    assert "*" not in _prod_settings().cors_origins_list
    assert settings.cors_origins_list and "*" not in settings.cors_origins_list


# ── 3. Rate limiting ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_login_exceeding_limit_returns_429(client: AsyncClient, monkeypatch):
    # A failed login (wrong creds) still consumes the rate-limit bucket, which is
    # the point of brute-force protection. Force a tiny limit to stay fast.
    monkeypatch.setattr(login_limiter, "limit", 2)
    for _ in range(2):
        resp = await client.post(
            "/auth/login",
            json={"email": f"none-{uuid.uuid4().hex}@example.com", "password": "x"},
        )
        assert resp.status_code == 401  # wrong creds, under the limit
    resp = await client.post(
        "/auth/login",
        json={"email": f"none-{uuid.uuid4().hex}@example.com", "password": "x"},
    )
    assert resp.status_code == 429
    assert "retry-after" in resp.headers


@pytest.mark.asyncio
async def test_normal_auth_traffic_passes(client: AsyncClient):
    email = f"rl-{uuid.uuid4().hex}@example.com"
    reg = await client.post(
        "/auth/register",
        json={
            "name": "Rate Limit Trader",
            "email": email,
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
    )
    assert reg.status_code == 201
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


# ── 4. Endpoint authorization ─────────────────────────────────────────────────
PROTECTED_GETS = [
    ("/api/v1/symbols"),
    ("/api/v1/account"),
    ("/api/v1/broker"),
    ("/api/v1/price/EURUSD"),
    ("/api/v1/candles/EURUSD"),
    ("/api/v1/ticks/EURUSD"),
    ("/api/v1/market-status"),
    ("/api/v1/indicators/EURUSD"),
    ("/api/v1/indicators/EURUSD/latest"),
    ("/api/v1/fibonacci/EURUSD"),
    ("/api/v1/smc/EURUSD"),
    ("/api/v1/smc/EURUSD/order-blocks"),
    ("/api/v1/smc/EURUSD/liquidity"),
    ("/api/v1/smc/EURUSD/fvg"),
    ("/api/v1/smc/EURUSD/premium-discount"),
    ("/api/v1/risk/pip-values"),
    ("/api/v1/risk/limits"),
    ("/api/v1/risk/status"),
    ("/api/v1/backtest/runs"),
    ("/auth/me"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_GETS)
async def test_protected_get_endpoints_require_token(client: AsyncClient, path):
    resp = await client.get(path)
    assert resp.status_code == 401


PROTECTED_POSTS = [
    ("/api/v1/ai/analyze", {}),
    ("/api/v1/backtest/run", {}),
    ("/api/v1/risk/calculate", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path,payload", PROTECTED_POSTS)
async def test_protected_post_endpoints_require_token(client: AsyncClient, path, payload):
    resp = await client.post(path, json=payload)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_public_endpoints_reachable_without_token(client: AsyncClient):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/docs")).status_code == 200
    reg = await client.post(
        "/auth/register",
        json={
            "name": "Public Trader",
            "email": f"pub-{uuid.uuid4().hex}@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        },
    )
    assert reg.status_code == 201


# ── 5. Secrets safety ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_broker_credentials_never_in_api_responses(
    client: AsyncClient, auth_headers, monkeypatch
):
    sentinel = f"OANDA_SECRET_{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "OANDA_API_KEY", sentinel)
    monkeypatch.setattr(settings, "OANDA_ACCOUNT_ID", f"acct-{uuid.uuid4().hex}")

    responses = []
    for path in (
        "/api/v1/symbols",
        "/api/v1/account",
        "/api/v1/broker",
        "/api/v1/price/EURUSD",
        "/api/v1/risk/status",
        "/auth/me",
    ):
        responses.append(await client.get(path, headers=auth_headers))
    # Logout + refresh responses carry tokens, not broker keys.
    responses.append(await client.post("/auth/logout", headers=auth_headers))

    for resp in responses:
        assert sentinel not in resp.text, f"secret leaked into {resp.url}"


@pytest.mark.asyncio
async def test_broker_credentials_never_persisted_to_db(
    db_session, client, auth_headers, monkeypatch
):
    sentinel = f"OANDA_DB_SECRET_{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "OANDA_API_KEY", sentinel)

    # Exercise authenticated endpoints that hit the DB.
    for path in (
        "/api/v1/symbols",
        "/api/v1/account",
        "/api/v1/risk/status",
    ):
        await client.get(path, headers=auth_headers)

    # Scan every mapped table: no row may contain the broker secret.
    from app.database import Base
    import app.models  # noqa: F401 - register all models

    for table in Base.metadata.sorted_tables:
        rows = (await db_session.execute(select(table))).all()
        for row in rows:
            assert sentinel not in str(row), f"secret persisted into table {table.name}"


@pytest.mark.asyncio
async def test_user_payload_never_exposes_hash(client: AsyncClient, auth_headers):
    # Ensure the autouse rate-limiter reset did not clear faked db rows.
    resp = await client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert "hashed_password" not in resp.text
    assert "password" not in resp.text
