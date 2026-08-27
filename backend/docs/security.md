# Security Hardening

This document describes the security hardening applied on the
`feature/security-hardening` branch and the authentication/authorization
contract every route must satisfy.

## Areas covered

1. **Production JWT startup guard** — `app/config.py` refuses to start in
   production (`APP_ENV=production|prod`) unless a real, non-placeholder,
   at-least-32-character `JWT_SECRET` is set. Missing/empty, the dev
   placeholder, and too-short secrets all raise `ValueError` at `Settings()`
   init, so a misconfigured production instance fails fast on boot instead of
   running insecure defaults.
2. **Strict CORS allow-list** — `CORS_ORIGINS` must be a non-empty JSON list of
   explicit origins. Wildcard (`*`) and empty lists are rejected because the
   middleware enables credentials. Origins are normalized (trimmed, trailing
   slash stripped); empty entries rejected.
3. **Auth rate limiting** — `app/utils/ratelimit.py` provides a dependency-free
   in-process sliding-window limiter wired into `register`, `login` and
   `refresh` (per-IP + per-account). Exceeding the limit returns `429` with a
   `Retry-After` header. State is per-process; a Redis-backed limiter can swap
   in at the same `allow(key)` seam for multi-worker deployments.
4. **Endpoint authorization** — every data endpoint below requires a valid
   Bearer token (401 without one). Public routes are limited to health, API
   docs, and the auth entry points.
5. **Secrets safety** — broker credentials (`OANDA_API_KEY`, `OANDA_ACCOUNT_ID`)
   are never included in API responses and are never persisted to the database;
   user password hashes are never returned by `/auth/me`.

## Endpoint → auth matrix

Legend: **Public** = reachable without a token; **Auth** = requires a valid
Bearer token (`Authorization: Bearer <jwt>`), returns `401` otherwise;
**Rate-limited** = additional 429 protection on top of public/anonymous access.

### Public / framework
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | Public | Liveness/health probe. |
| GET | `/docs` | Public | OpenAPI Swagger UI (framework). |
| GET | `/redoc` | Public | ReDoc UI (framework). |
| GET | `/docs/oauth2-redirect` | Public | Swagger OAuth2 redirect (framework). |
| GET | `/openapi.json` | Public | OpenAPI schema (framework). |

### Auth (`/auth`)
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/auth/register` | Public | Rate-limited per IP + per email. |
| POST | `/auth/login` | Public | Rate-limited per IP + per account. |
| POST | `/auth/forgot-password` | Public | Always returns success (anti-enumeration). No rate limit yet. |
| POST | `/auth/refresh` | Public* | Rate-limited per IP; requires a valid refresh token (decoded before issue). |
| GET | `/auth/me` | **Auth** | Returns current user profile (no hash). |
| PATCH | `/auth/settings` | **Auth** | Updates current user settings. |
| POST | `/auth/logout` | **Auth** | Client-side token discard. |

### Market data (`/api/v1`)
| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/symbols` | **Auth** |
| GET | `/api/v1/account` | **Auth** |
| GET | `/api/v1/broker` | **Auth** |
| GET | `/api/v1/price/{symbol}` | **Auth** |
| GET | `/api/v1/candles/{symbol}` | **Auth** |
| GET | `/api/v1/ticks/{symbol}` | **Auth** |
| GET | `/api/v1/market-status` | **Auth** |
| GET | `/api/v1/market-status/{symbol}` | **Auth** |

### Indicators (`/api/v1`)
| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/indicators/{symbol}` | **Auth** |
| GET | `/api/v1/indicators/{symbol}/latest` | **Auth** |
| GET | `/api/v1/support-resistance/{symbol}` | **Auth** |
| GET | `/api/v1/fibonacci/{symbol}` | **Auth** |

### SMC / ICT (`/api/v1`)
| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/smc/{symbol}` | **Auth** |
| GET | `/api/v1/smc/{symbol}/type/{structure_type}` | **Auth** |
| GET | `/api/v1/smc/{symbol}/order-blocks` | **Auth** |
| GET | `/api/v1/smc/{symbol}/liquidity` | **Auth** |
| GET | `/api/v1/smc/{symbol}/fvg` | **Auth** |
| GET | `/api/v1/smc/{symbol}/premium-discount` | **Auth** |

### AI decision engine (`/api/v1`)
| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/ai/analyze` | **Auth** |
| POST | `/api/v1/ai/analyze-batch` | **Auth** |
| GET | `/api/v1/ai/recommendation/{symbol}` | **Auth** |
| GET | `/api/v1/ai/recommendations` | **Auth** |

### Risk management (`/api/v1/risk`)
| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/risk/calculate` | **Auth** |
| GET | `/api/v1/risk/pip-values` | **Auth** |
| GET | `/api/v1/risk/limits` | **Auth** |
| PUT | `/api/v1/risk/limits` | **Auth** |
| GET | `/api/v1/risk/status` | **Auth** |
| POST | `/api/v1/risk/reset` | **Auth** |

### Backtesting (`/api/v1/backtest`)
| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/backtest/run` | **Auth** |
| GET | `/api/v1/backtest/runs` | **Auth** |
| GET | `/api/v1/backtest/runs/{run_id}` | **Auth** |
| DELETE | `/api/v1/backtest/runs/{run_id}` | **Auth** |

## Authorization sanity pass (final)

Every route under `/api/v1` — across market data, indicators, SMC, AI, risk,
and backtest routers — goes through `get_current_user` (`Depends`), which
returns **401** when no valid token is presented. A review of all
`@router.*` decorators confirmed:

- No data endpoint under `/api/v1` is accidentally unauthenticated.
- The only unauthenticated POSTs are the auth entry points
  (`register`, `login`, `forgot-password`, `refresh`), which must be
  reachable to obtain a token and are protected by rate limiting.
- `/health` and the framework docs/OpenAPI routes are intentionally public.

The `test_security.py` suite enforces this contract: every protected GET/POST
listed above is asserted to return `401` without a token, public endpoints are
asserted reachable, and broker secrets are asserted absent from both API
payloads and the database.

## Test coverage
See `backend/tests/test_security.py` (JWT guard, CORS, rate limiting, endpoint
authorization, secrets safety).
