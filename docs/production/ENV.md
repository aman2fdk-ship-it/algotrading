# ForexAI Terminal — Environment Inventory

Every variable the stack reads, what it does, where its value comes from, whether it is a secret, and
how staging and production differ. **This document contains variable names only — never values.**

## TOC

1. [The rules](#1-the-rules)
2. [Owner-provided credentials (deploy-time)](#2-owner-provided-credentials-deploy-time)
3. [Backend runtime variables](#3-backend-runtime-variables)
4. [Frontend build-time variables](#4-frontend-build-time-variables)
5. [Staging vs production](#5-staging-vs-production)
6. [Staging provenance (this machine)](#6-staging-provenance-this-machine)
7. [Separation rule and how to verify it](#7-separation-rule-and-how-to-verify-it)
8. [Rotation](#8-rotation)

---

## 1. The rules

1. **Secrets live only in the platform Secrets store** (Render environment/secrets for the backend,
   Vercel environment variables for the frontend, and the owner's password manager for anything used
   by tooling). They are never written into the repository, a doc, a script, a Dockerfile, an image,
   a log line or a chat message.
2. **Scripts read names from the environment**, never literals: `scripts/deploy-prod.sh` and
   `scripts/rollback-prod.sh` require the operator to export the variables and refuse to run without
   them. No credential is ever typed into a file.
3. **Staging and production environments are fully separate**: separate PostgreSQL, separate Redis,
   separate `JWT_SECRET`, separate origins, separate credentials. Sharing a database, a Redis
   instance or a secret between them is prohibited (see §7).
4. Some variables are **deploy-time only** (used by tooling, never by the running app) — see §2. They
   must not be present in the backend's runtime environment.
5. Explicit is better than default in production: the app is written to work with defaults in
   development, and to **fail fast** on insecure production configuration.

---

## 2. Owner-provided credentials (deploy-time)

Store these under exactly these names. **BLOCKED-ON-OWNER** until the corresponding account exists.

| Name | Secret? | Read by | Comes from (provider page) | Purpose |
|---|---|---|---|---|
| `TIGER_PUBLIC_KEY` | ✅ | ops tooling | Tiger Cloud console → account/API keys | identify the Tiger project/service programmatically |
| `TIGER_SECRET_KEY` | ✅ | ops tooling | Tiger Cloud console → account/API keys | authenticate to Tiger for provisioning/inspection |
| `TIGER_PROJECT_ID` | ❌ (identifier) | ops tooling | Tiger Cloud console → project page | select the production project |
| `UPSTASH_REDIS_REST_URL` | ❌ (identifier) | ops tooling | Upstash console → database → REST API | REST endpoint for ops automation |
| `UPSTASH_REDIS_REST_TOKEN` | ✅ | ops tooling | Upstash console → database → REST API | token for the REST endpoint |
| `VERCEL_TOKEN` | ✅ | deploy tooling | Vercel account settings → Tokens | deploy/inspect the frontend project |
| `RENDER_API_KEY` | ✅ | deploy tooling | Render account settings → API Keys | trigger/verify the backend deploy |
| `RENDER_SERVICE_ID` | ❌ (identifier) | deploy tooling | Render service page | select the backend service for API calls |

Derived values that come **out of** the provisioning step and go **into** the backend's runtime
environment (never into this repo): `DATABASE_URL`, `REDIS_URL` (see §3.1 / §3.2). `JWT_SECRET` is
generated, not provided: `openssl rand -hex 32`.

The backend does **not** consume `TIGER_*`, `UPSTASH_*`, `VERCEL_TOKEN` or `RENDER_API_KEY`. Adding
them to the runtime environment only widens the blast radius if the container is compromised.

---

## 3. Backend runtime variables

Source of truth: `backend/app/config.py` (pydantic-settings, `env_file=".env"`, `extra="ignore"`).
Values are read from the process environment; a `backend/.env` file in the working directory would
also be read — production must rely on injected environment variables only and must never ship a
`.env` (it is gitignored, so a git-based build never sees one).

### 3.1 Required in production

| Variable | Purpose | Secret? | Notes |
|---|---|---|---|
| `APP_ENV` | selects the production security guard | ❌ | set to `production`. Any value in `{production, prod}` triggers the guard; the default `development` disables it |
| `DATABASE_URL` | async PostgreSQL DSN (asyncpg), used by the app **and** by Alembic | ✅ | `postgresql+asyncpg://…` + TLS parameter **`ssl=require`** (must not be `sslmode`, see §3.4) |
| `DATABASE_URL_SYNC` | libpq-style DSN used by `psql`/`pg_dump`/`pg_restore` | ✅ | `postgresql://…` + `sslmode=require`. Declared in settings for parity; Alembic does **not** read it |
| `REDIS_URL` | managed Redis DSN (cache + readiness probe) | ✅ | `rediss://default:…@host:port/0` for Upstash TLS; see the readiness TLS gap in `OPERATIONS.md` §8.1 |
| `JWT_SECRET` | signs/verifies access and refresh tokens | ✅ | production guard: **required**, must not equal the development placeholder `dev-secret-key-change-in-production`, and must be **≥ 32 characters**. Generate with `openssl rand -hex 32`. A unique value per environment |
| `CORS_ORIGINS` | explicit browser-origin allow-list (JSON list) | ❌ | e.g. `["https://app.example.com"]`. Wildcard `"*"` is **rejected** (credentials are enabled); must be non-empty; entries are normalized (whitespace and trailing slashes stripped). Never include a staging origin in production |
| `MARKET_DATA_PROVIDER` | selects the market-data source | ❌ | `auto` (default) → OANDA when credentials are present, else MT5 when enabled, else mock; or force `oanda` \| `mt5` \| `mock`. Unknown values warn and fall back to mock |

### 3.2 Market-data provider (broker REST demo feed + fallbacks)

| Variable | Purpose | Secret? | Notes |
|---|---|---|---|
| `OANDA_API_KEY` | broker REST API token (demo/practice) | ✅ | absent ⇒ factory degrades to mock with a warning |
| `OANDA_ACCOUNT_ID` | broker account identifier | ✅ (account id) | required together with the key |
| `OANDA_ENV` | `practice` \| `live` | ❌ | keep `practice` for the first release |
| `OANDA_BASE_URL` | overrides the host derived from `OANDA_ENV` | ❌ | for a compatible broker endpoint or a test double |
| `OANDA_TIMEOUT_S` | HTTP timeout per request | ❌ | default 10 s |
| `OANDA_REQUEST_DELAY_S` | optional inter-request sleep (rate-limit padding) | ❌ | default 0 |
| `MT5_ENABLED` | enable the MT5 client path | ❌ | staging sets `false`; production only with real MT5 credentials |
| `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH` | MT5 account connection | ✅ (`MT5_PASSWORD`) | not part of the first release |
| `MT5_HEARTBEAT_INTERVAL_S`, `MT5_RECONNECT_INITIAL_BACKOFF_S`, `MT5_RECONNECT_MAX_BACKOFF_S`, `MT5_RECONNECT_MAX_RETRIES` | MT5 liveness/reconnect tuning | ❌ | reconnection manager only runs when MT5 is connected |

### 3.3 Caching, auth, background services and tuning

| Variable | Purpose | Secret? | Default |
|---|---|---|---|
| `REDIS_CACHE_ENABLED` | enable the Redis cache layer | ❌ | `True` |
| `REDIS_CACHE_TTL_S` | cache TTL (analysis values may lag up to this long) | ❌ | `30` |
| `JWT_ALGORITHM` | token signing algorithm | ❌ | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | access-token lifetime | ❌ | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | refresh-token lifetime | ❌ | `7` |
| `AUTH_LOGIN_RATE_LIMIT` | login attempts per window (per IP + per account) | ❌ | `20` |
| `AUTH_REGISTER_RATE_LIMIT` | registrations per window (per IP + per email) | ❌ | `10` |
| `AUTH_REFRESH_RATE_LIMIT` | refreshes per window (per IP) | ❌ | `60` |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | rate-limit window | ❌ | `60.0` |
| `TICK_COLLECTOR_ENABLED` | tick collection service | ❌ | `True` (runs only when a live provider is connected) |
| `CANDLE_SYNC_ENABLED` | candle sync **and** the indicator/SMC calculators | ❌ | `True` |
| `SESSION_DETECTOR_ENABLED` | trading-session detection | ❌ | `True` |
| `MARKET_STATUS_MONITOR_ENABLED` | market open/close monitor | ❌ | `True` |
| `RECONNECTION_MANAGER_ENABLED` | provider reconnection supervisor | ❌ | `True` |
| `TICK_POLL_INTERVAL_MS` | tick poll cadence | ❌ | `500` |
| `TICK_BATCH_SIZE` | ticks per write batch | ❌ | `50` |
| `CANDLE_SYNC_INTERVAL_S` | candle sync cadence | ❌ | `30` |
| `CANDLE_BACKFILL_COUNT` | candles fetched per backfill | ❌ | `200` |
| `PORT` | port the container binds | ❌ | injected by the host. The image's `CMD` hardcodes `8000`; set `PORT=8000` **or** override the start command with `--port $PORT` |

Background-service gating (verified in the staging boot log): with `MT5_ENABLED=false` and no live
provider, `mt5_client` stays `None`, so tick collection, candle sync, market-status monitoring and
the reconnection manager do not start — that is expected in mock/no-credential mode, not a defect.
The session detector and the indicator/SMC calculators (gated by `CANDLE_SYNC_ENABLED`) run
regardless.

### 3.4 Callout — TLS parameters on the database DSNs (verified locally)

| Variable | Driver | Correct TLS parameter | Wrong |
|---|---|---|---|
| `DATABASE_URL` | asyncpg (async) | `?ssl=require` (or `ssl=verify-full`) | `sslmode=require` → `TypeError: connect() got an unexpected keyword argument 'sslmode'` |
| `DATABASE_URL_SYNC` | libpq / psycopg2 (`psql`, `pg_dump`) | `?sslmode=require` | — |

Managed providers hand you a `sslmode=` string; convert it for `DATABASE_URL`. Do not add
`channel_binding=require` to the async DSN either — it is passed through as an unsupported keyword.
`scripts/deploy-prod.sh --preflight` enforces this.

---

## 4. Frontend build-time variables

| Variable | Purpose | Secret? | Notes |
|---|---|---|---|
| `VITE_API_URL` | API base URL baked into the bundle (`frontend/src/lib/api.ts` prefixes every request with it) | ❌ | Vite inlines it **at build time** — changing it requires a rebuild, not a restart. Leave unset for same-origin (recommended: proxy `/api/*` and `/auth/*` from the Vercel origin to Render). No trailing slash. If set, the frontend origin must also be added to the backend's `CORS_ORIGINS` |

No secret belongs in a frontend variable: everything prefixed `VITE_` is public in the shipped bundle.

---

## 5. Staging vs production

| Aspect | Staging (this machine) | Production (managed services) |
|---|---|---|
| Backend entry point | `uvicorn app.main:app` on `127.0.0.1:8013`, started from `backend/` with `/opt/forexai-venv` | Render container from `backend/Dockerfile`, binds `0.0.0.0:$PORT` |
| Frontend | `node /home/team/shared/staging/forexai-fe-server.js` on `127.0.0.1:8081` (static `frontend/dist` + proxy to `:8013`, no rewrite). Port 3000 is the team's separate public marketing site | Vercel static build of `frontend/dist` on the owner's domain (HTTPS) |
| PostgreSQL | local PG 16, database/role `forexai_staging` on `127.0.0.1:5432` | Tiger Cloud managed PostgreSQL (TLS) |
| Redis | local Redis 7, `requirepass` + AOF, `127.0.0.1:6379` | Upstash managed Redis (TLS) |
| `APP_ENV` | unset → `development` (guard off) | **`production`** (guard on: real secret required) |
| `JWT_SECRET` | staging-only value (from `.staging-secrets`) | distinct production secret, ≥ 32 chars |
| `CORS_ORIGINS` | `["http://127.0.0.1:8081","http://localhost:3000"]` | production HTTPS origin(s) only |
| Market data | `MT5_ENABLED=false`, provider `auto` → **mock** | broker REST **demo** feed (`MARKET_DATA_PROVIDER=oanda`, `OANDA_ENV=practice`); mock as fallback |
| TLS | none (loopback HTTP) | HTTPS everywhere; managed PG/Redis require TLS |
| Secrets location | `/home/team/shared/.staging-secrets` (mode 600, machine-local) | platform Secrets store (Render env / Vercel env / owner's password manager) |
| Migrations | `alembic upgrade head` from `backend/` with `/tmp/staging_env.sh` sourced | Render pre-deploy command with injected `DATABASE_URL` |
| Persistence of state | local PG data on this machine; rebuildable via the staging rebuild script | provider-managed, backed up |
| Purpose | validation, E2E, verification runs | real users, live data, advisory signals only |

**Not permitted:** pointing production at the staging database or Redis; reusing the staging
`JWT_SECRET`; adding an internal/loopback address to production `CORS_ORIGINS`; copying a staging DSN
into a production variable (or the reverse).

---

## 6. Staging provenance (this machine)

Recorded by name only — no values:

- `/home/team/shared/.staging-secrets` (mode 600) holds `STAGING_DB_PASSWORD`,
  `STAGING_REDIS_PASSWORD`, `STAGING_JWT_SECRET`.
- `/home/team/shared/staging/rebuild_staging.sh` (idempotent, one command) composes those into
  `/tmp/staging_env.sh` (mode 600), which exports `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`,
  `JWT_SECRET`, `CORS_ORIGINS`, `MT5_ENABLED` for the staging backend and the seed/test tooling.
  Run it as `sudo /home/team/shared/staging/rebuild_staging.sh`, or source the env file directly.
- Staging rebuild steps and the full PASS checklist: see
  `/home/team/shared/staging-env-inventory.md` and the rehearsal notes in
  `/home/team/shared/verification-observability-merged.md`.

Staging variables are **staging-class credentials**: they never leave this machine and are never
reused for production.

---

## 7. Separation rule and how to verify it

**Rule:** production must be able to lose staging entirely (and vice versa) with zero effect. That
requires, at minimum, different databases, different Redis instances, different `JWT_SECRET` values,
different origins and different credential sets.

Verification checklist (all of it is doable without printing a single value):

- [ ] **Names, not values**: compare the *variable names* exposed by each environment; production must
      not contain a staging-named secret (`STAGING_*`) or a loopback host in `DATABASE_URL` /
      `REDIS_URL`.
- [ ] **Secrets differ** — compare fingerprints, never the values:
      `printf '%s' "$JWT_SECRET" | sha256sum` in each environment must produce different digests.
- [ ] **Origin hygiene**: production `CORS_ORIGINS` contains only HTTPS production origins — no
      `127.0.0.1`, no `localhost`, no staging host, no `*`.
- [ ] **Database hygiene**: the production `DATABASE_URL_SYNC` host is the managed service
      (`psql "$DATABASE_URL_SYNC" -c 'select current_database(), inet_server_addr();'`); the database
      name is not `forexai_staging`.
- [ ] **Redis hygiene**: `redis-cli -u "$REDIS_URL" DBSIZE` on production is a production-sized,
      production-flavoured key space, and the host is not loopback.
- [ ] **No cross-env leakage in artifacts**: `grep -RIn 'STAGING' docs/ scripts/ backend/Dockerfile
      frontend/` finds no staging secret *name* used as a production variable.
- [ ] **Repo hygiene**: nothing under version control matches a secret pattern (`git ls-files` +
      a secret scanner such as `gitleaks`/`trufflehog` on the history).
- [ ] **Log hygiene**: no credential appears in the platform log stream (§6 of `OPERATIONS.md`).

---

## 8. Rotation

| Variable | When | Procedure | Blast radius |
|---|---|---|---|
| `JWT_SECRET` | on suspicion of exposure, or scheduled | generate a new `openssl rand -hex 32`, update the Secrets store, restart the backend, verify old tokens fail | **all sessions invalidated** — users log in again |
| `DATABASE_URL` / password | on exposure or provider rotation | rotate at the provider, update the variable atomically with any DSN change, restart the backend, confirm `/health/ready` | full outage if done wrong — do it in a change window |
| `REDIS_URL` / token | on exposure or provider rotation | rotate at Upstash, update the variable, restart the backend; cache warms itself | brief cold cache; nothing durable is stored |
| `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` | on exposure or expiry | rotate in the broker console, update the variable, restart; verify `components.market_data` is `ok` | analysis falls back to mock until fixed |
| `VERCEL_TOKEN`, `RENDER_API_KEY` | on exposure, or annually | revoke in the provider, issue a new one, update the Secrets store | deploy tooling only — the running app is unaffected |
| `TIGER_*`, `UPSTASH_*` | on exposure, or annually | same as above | ops tooling only |

Every rotation: record it (date, variable name, who, why), never the value. After a rotation, run
`scripts/deploy-prod.sh --preflight` and `--verify` before declaring it done.
