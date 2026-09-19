# ForexAI Terminal — Production Deployment & Operations Pack

Status: **prepared, not executed.** No production deployment has happened. Every step that needs a
managed-service account or a credential is marked **BLOCKED-ON-OWNER**. This pack contains **no
secret values** — only environment-variable *names* (see [`ENV.md`](ENV.md)).

Derived from the battle-tested local staging rebuild (`/home/team/shared/staging/rebuild_staging.sh`,
verdict A, 12/12 checks, idempotent). The staging script remains the source of truth for the *local*
stack; these documents translate its proven steps onto managed services.

## Contents

| Document | What it covers |
|---|---|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Reproducible production deployment: prerequisites, provider-by-provider setup, build commands, migration step, startup order, health verification |
| [`OPERATIONS.md`](OPERATIONS.md) | Day-2 procedures: migrations + rollback, backup/restore, restart order, logs, incident-response runbook, known gaps |
| [`ENV.md`](ENV.md) | Environment inventory: every variable, provenance, secret/not, staging vs production differences, separation rule |
| [`../../scripts/deploy-prod.sh`](../../scripts/deploy-prod.sh) | Executable deploy: preflight → build → migrate → deploy → health-wait with timeout |
| [`../../scripts/rollback-prod.sh`](../../scripts/rollback-prod.sh) | Rollback helper (dry-run by default): migration downgrade + provider rollback hints |

## Scope of the first production release (fixed by the business plan)

**LIVE DATA + ANALYSIS + SIGNAL/PAPER TRADING ONLY.** Advisory output (BUY / SELL / WAIT) with
reasoning and confidence; **no automatic real-money execution**. No broker order-routing code is
enabled in this release — an automated execution path requires signal validation, backtesting,
forward testing, risk rules, position sizing, SL/TP validation, daily-loss controls, drawdown
monitoring, an audit trail, broker execution testing, failure/reconnection handling and an
emergency kill switch, none of which are in scope here.

## Target architecture (managed services)

| Layer | Service | Credential / config names | Status |
|---|---|---|---|
| Frontend (static SPA) | Vercel | `VERCEL_TOKEN` (deploy), `VITE_API_URL` (build) | **BLOCKED-ON-OWNER** |
| Backend API (container) | Render | `RENDER_API_KEY` (deploy), runtime env vars | **BLOCKED-ON-OWNER** |
| PostgreSQL | Tiger Cloud (managed PG) | `TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID` → yield `DATABASE_URL` | **BLOCKED-ON-OWNER** |
| Redis | Upstash (managed Redis) | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` → yield `REDIS_URL` | **BLOCKED-ON-OWNER** |
| Market data | Broker REST demo feed (OANDA practice-style) behind the provider abstraction; **mock remains the fallback** | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, `MARKET_DATA_PROVIDER` | **BLOCKED-ON-OWNER** (demo credentials) |
| Auth | JWT with production-only secret, explicit-origin CORS, rate limiting | `JWT_SECRET`, `CORS_ORIGINS`, `APP_ENV` | Code-ready (guard verified by tests) |
| Domain / CORS origin | owner-chosen production domain | `CORS_ORIGINS`, Vercel domain | **BLOCKED-ON-OWNER** (decision) |

Local staging (this machine) is **completely separate** from production: separate PostgreSQL, separate
Redis, separate `JWT_SECRET`, separate origins. No staging secret may be copied into production — see
[`ENV.md`](ENV.md) §5–§7.

## What was verified locally while writing this pack

| Check | How | Result |
|---|---|---|
| `scripts/deploy-prod.sh --preflight` fails cleanly on an incomplete environment | run with no env vars set | ✅ fails, exit 1, lists every missing variable name |
| `scripts/deploy-prod.sh --preflight` passes on a production-shaped environment | synthetic prod env (`APP_ENV=production`, TLS DSN, https origin, strong secret) | ✅ passes, exit 0 |
| Preflight rejects a `sslmode=` async DSN (a real asyncpg failure mode) | `DATABASE_URL=...?sslmode=require` | ✅ fails with the exact fix (`?ssl=require`) |
| Health-wait loop against a real running backend | staging API on `http://127.0.0.1:8013` (up during this session) | ✅ `/health/live` 200 + `/health/ready` 200 `status=ok` |
| Health-wait loop timeout path | `--api-url` pointed at a closed port, 4 s timeout | ✅ exits non-zero with rollback hint |
| Alembic DSN handling / TLS parameter semantics | inspected `alembic/env.py` + exercised SQLAlchemy & asyncpg locally | ✅ documented (see the `ssl` vs `sslmode` callout in `DEPLOYMENT.md` §4.1) |

Everything else (creating accounts, injecting real credentials, DNS, live broker feed) is **not
executed** and is marked BLOCKED-ON-OWNER where it occurs.
