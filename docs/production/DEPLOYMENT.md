# ForexAI Terminal — Production Deployment Guide

Status: **prepared, not executed.** Derived from the proven staging rebuild
(`/home/team/shared/staging/rebuild_staging.sh`). Steps that need an owner-provided credential are
marked **BLOCKED-ON-OWNER** with the exact credential name. **No secret values appear in this
document** — variable names only.

## TOC

1. [Target topology](#1-target-topology)
2. [Prerequisites](#2-prerequisites)
3. [Environment variables (names only)](#3-environment-variables-names-only)
4. [Provider setup, step by step](#4-provider-setup-step-by-step)
   - 4.1 [Tiger Cloud — managed PostgreSQL](#41-tiger-cloud--managed-postgresql)
   - 4.2 [Upstash — managed Redis](#42-upstash--managed-redis)
   - 4.3 [Render — backend container](#43-render--backend-container)
   - 4.4 [Market data — broker REST demo feed](#44-market-data--broker-rest-demo-feed)
   - 4.5 [Vercel — frontend SPA](#45-vercel--frontend-spa)
5. [Build commands](#5-build-commands)
6. [Database migration step (`alembic upgrade head`)](#6-database-migration-step-alembic-upgrade-head)
7. [Startup order](#7-startup-order)
8. [Health-check verification](#8-health-check-verification)
9. [One-command deploy (`scripts/deploy-prod.sh`)](#9-one-command-deploy-scriptsdeploy-prodsh)
10. [Post-deploy verification checklist](#10-post-deploy-verification-checklist)
11. [Rollback](#11-rollback)
12. [Blocked-on-owner summary](#12-blocked-on-owner-summary)

---

## 1. Target topology

```
                 owner domain (HTTPS, owner decision)         BLOCKED-ON-OWNER: domain choice
                          │
              ┌───────────┴────────────┐
              │                        │
        Vercel (static SPA)      Render (uvicorn container)
        frontend/dist            backend/Dockerfile, $PORT
              │                        │
              │  /api/v1/*, /auth/*    ├── Tiger Cloud  PostgreSQL (DATABASE_URL)
              └────────────────────────┤                migrations via alembic upgrade head
                  same-origin (opt A)  ├── Upstash      Redis      (REDIS_URL)
                  or CORS (opt B)      └── OANDA REST demo feed     (MARKET_DATA_PROVIDER)
```

Components and the code they come from:

| Component | Source in repo | Runs as |
|---|---|---|
| Backend API | `backend/` (FastAPI, `app.main:app`), `backend/requirements.txt`, `backend/Dockerfile` | Render container (`uvicorn`, port from `$PORT`) |
| Frontend | `frontend/` (Vite + React + TS + Tailwind) → `frontend/dist` | Vercel static build |
| Migrations | `backend/alembic/` (`alembic upgrade head`) | Render pre-deploy command or manual step (§6) |
| Self-hosted alternative | `frontend/nginx.conf`, `docker-compose.yml` | Any Docker host / local — used by staging |

API surface (relevant to routing, CORS and health checks): **auth is unversioned at `/auth/*`**;
everything else is `/api/v1/*`; health endpoints are `/health`, `/health/live`, `/health/ready`,
`/health/metrics`, `/health/metrics/prometheus`. Any reverse proxy must forward paths **unchanged**
(no rewrite) — this is how `frontend/nginx.conf` and the staging FE proxy are configured.

---

## 2. Prerequisites

**Owner-provided credentials (all BLOCKED-ON-OWNER — see §12):**

| Name | Used for |
|---|---|
| `VERCEL_TOKEN` | deploying the frontend from CI/local (`scripts/deploy-prod.sh --deploy`) |
| `RENDER_API_KEY` | triggering/verifying the backend deploy (`scripts/deploy-prod.sh --deploy`) |
| `TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID` | provisioning/inspecting the managed PostgreSQL (yields `DATABASE_URL`) |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | provisioning/inspecting the managed Redis (yields `REDIS_URL`) |
| Broker REST demo credentials (`OANDA_API_KEY`, `OANDA_ACCOUNT_ID`) | live demo market data |

Store them in the platform Secrets store under exactly those names. `VERCEL_TOKEN` and
`RENDER_API_KEY` are **deploy-time only** — they must never be set as runtime variables on the
backend. See [`ENV.md`](ENV.md) §2.

**Local/CI tooling:** `git`, `curl`; `python3.12` + `pip` for migrations if run outside the platform;
`node 20+`/`npm` for the frontend build; `docker` only if you choose to build the backend image
locally; `psql` (or the Tiger console) for DDL/backup verification.

---

## 3. Environment variables (names only)

Full inventory, provenance and secret classification: [`ENV.md`](ENV.md). The minimum set the backend
refuses to run without in production:

| Name | Notes |
|---|---|
| `APP_ENV` | must be `production` — enables the fail-fast security guard |
| `DATABASE_URL` | `postgresql+asyncpg://…` **with the `ssl` parameter, not `sslmode`** (§4.1) |
| `DATABASE_URL_SYNC` | declared for parity; Alembic actually reuses `DATABASE_URL` (§6) |
| `REDIS_URL` | managed Redis DSN |
| `JWT_SECRET` | ≥ 32 chars, randomly generated, **never** the development placeholder |
| `CORS_ORIGINS` | JSON list of explicit HTTPS origins, never `["*"]` |
| `MARKET_DATA_PROVIDER` | `auto` \| `oanda` \| `mt5` \| `mock` (mock is the safe fallback) |

Generate the production secret (value stays on the platform, never in this repo):

```bash
openssl rand -hex 32     # paste the output into the platform Secrets store as JWT_SECRET
```

Two guards from `backend/app/config.py` gate startup and are worth knowing before you deploy:

- `APP_ENV=production` **fails app import** if `JWT_SECRET` is missing, is the placeholder
  `dev-secret-key-change-in-production`, or is shorter than 32 characters.
- `CORS_ORIGINS` must be a non-empty JSON list of explicit origins; `"*"` is rejected because
  credentials are enabled. Entries are normalized (whitespace and **trailing slashes stripped**).

---

## 4. Provider setup, step by step

> Order matters: PostgreSQL and Redis first (the backend cannot become ready without them), then the
> backend, then the frontend pointing at it.

### 4.1 Tiger Cloud — managed PostgreSQL

**BLOCKED-ON-OWNER:** the service must be created in the owner's Tiger Cloud account
(`TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID`). No production database exists yet.

1. **Provision** a PostgreSQL service for the production project (managed, single production
   database; do **not** reuse the staging database).
2. **Retrieve** the connection string from the service's "Connect" panel.
3. **Build the two DSNs** from it and store them as `DATABASE_URL` / `DATABASE_URL_SYNC` in the
   Render Secrets store:

   | Variable | Shape | TLS parameter |
   |---|---|---|
   | `DATABASE_URL` | `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME` | `?ssl=require` |
   | `DATABASE_URL_SYNC` | `postgresql://USER:PASSWORD@HOST:PORT/DBNAME` | `?sslmode=require` |

   > **Callout — the `ssl` vs `sslmode` trap (verified locally against this repo's stack).**
   > The app and Alembic run on the **asyncpg** driver, which does **not** accept `sslmode`:
   > `asyncpg.connect(...)` raises `TypeError: connect() got an unexpected keyword argument 'sslmode'`
   > because SQLAlchemy passes URL query parameters straight through. Use **`ssl=require`** (or
   > `ssl=verify-full`) in `DATABASE_URL`. `sslmode=` is only correct for the libpq/psycopg2-style
   > `DATABASE_URL_SYNC`. A managed provider's copy-paste string normally uses `sslmode` — convert it.
   > `scripts/deploy-prod.sh --preflight` rejects `sslmode` in `DATABASE_URL` for this reason.
   >
   > Do not add `channel_binding=require` either — it is likewise passed to asyncpg as a keyword.

4. **Verify connectivity** before deploying the app (uses the variable, so no literal secret is typed):

   ```bash
   psql "$DATABASE_URL_SYNC" -c 'select version(), current_database();'
   ```

5. **Allow the backend host** if the provider has an IP allow-list; prefer TLS + SCRAM
   password auth, strongest setting available.
6. **Confirm backups** are enabled on the service (see [`OPERATIONS.md`](OPERATIONS.md) §4).
7. **Seed reference data**: symbol rows are created by the migration/seed path; the staging flow used
   `staging/seed_market_data.py` for synthetic candles/ticks. In production the provider feed fills
   candles/ticks — no synthetic seeding in production.

### 4.2 Upstash — managed Redis

**BLOCKED-ON-OWNER:** `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` (owner's Upstash account).

1. **Provision** a Redis database in the production region closest to the backend region; enable TLS
   (default) and eviction/`noeviction` policy appropriate for a cache.
2. **Copy the TCP DSN** into `REDIS_URL` (the app speaks the Redis protocol, not the REST API):
   `rediss://default:PASSWORD@HOST:PORT/0`.
3. The REST credentials (`UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`) are for console/ops
   automation; the backend does **not** consume them today.
4. **Verify** (uses `REDIS_URL`, no literal secret):

   ```bash
   redis-cli -u "$REDIS_URL" PING     # expected: PONG
   ```

> **Known gap — TLS DSNs and the readiness probe.** `app/services/health.py::check_redis` builds its
> client from the parsed host/port/password of `REDIS_URL` **without** enabling TLS, so a `rediss://`
> DSN will make `GET /health/ready` report `redis: down` and return **503** — which in turn makes a
> platform health check fail and restart-loop the service. The API itself stays up (the cache layer
> degrades gracefully by design), but readiness is wrong. Fix options and the exact code seam are in
> [`OPERATIONS.md`](OPERATIONS.md) §8 (Known gaps). `--preflight` warns when `REDIS_URL` starts with
> `rediss://`. Treat this as a **code fix required before/at first production deploy**.

### 4.3 Render — backend container

**BLOCKED-ON-OWNER:** `RENDER_API_KEY` (owner's Render account) for scripted deploys; the service can
also be created in the Render dashboard.

1. Create a **Web Service → Build from a Git repository** (this repo), branch = the production branch.
2. **Runtime: Docker.** Dockerfile path `backend/Dockerfile`, **Docker build context `backend/`**.
3. **Start command / port:** the image's `CMD` hardcodes `--port 8000`. Render injects its own
   `PORT`, so do **one** of these:
   - set the service **Start Command** to
     `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (preferred), **or**
   - set an env var `PORT=8000` to match the image (only if you keep the default `CMD`).
   Binding to `0.0.0.0` (not `127.0.0.1`) is mandatory — the staging stack deliberately uses loopback,
   production must not.
4. **Health check path:** `/health/ready` (returns 200 only when API + PostgreSQL + Redis are ok; a
   degraded feed alone still returns 200 — see §8).
5. **Pre-deploy command:** `python -m alembic upgrade head` (run from `backend/`; see §6). If the
   platform does not support pre-deploy hooks on your plan, run §6 manually before switching traffic.
6. **Environment / Secrets:** add every runtime variable from [`ENV.md`](ENV.md) §3 —
   `APP_ENV=production`, `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, `JWT_SECRET`,
   `CORS_ORIGINS`, `MARKET_DATA_PROVIDER`, and the chosen `OANDA_*` / `MT5_*` values.
   Never add `VERCEL_TOKEN` or `RENDER_API_KEY` here.
7. **Scaling:** run **one** instance to start. Auth rate limiting is per-process and in-memory
   (`app/utils/ratelimit.py`), so N instances multiply the effective limit and a restart clears the
   counters; move the limiter to a shared backend before scaling out.
8. **Deploys are stateless**: the container holds no data; the local `backend/.env` file is not
   needed (and must not be baked into an image — a git-based build never sees it, since `.env` is
   gitignored).
9. From the service page, note the service **ID** and the public URL: they feed
   `RENDER_SERVICE_ID` and `PROD_API_URL` for the deploy script (§9).

### 4.4 Market data — broker REST demo feed

**BLOCKED-ON-OWNER:** broker REST **demo** credentials. Until they exist, keep the mock provider —
this is an explicitly supported, documented fallback, not a broken state.

1. Obtain demo (practice) REST credentials from the broker; store `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`.
2. Set `MARKET_DATA_PROVIDER=oanda` (or leave `auto`, which selects OANDA when credentials exist) and
   keep `OANDA_ENV=practice` for the first release. `OANDA_BASE_URL` overrides the host if needed.
3. **Degradation rule:** if the credentials are missing or invalid, the factory logs a warning and
   falls back to **mock**; readiness reports `market_data: degraded` while the API stays 200. Never let
   a feed problem take the API down.
4. MT5 remains available (`MARKET_DATA_PROVIDER=mt5`, `MT5_ENABLED=true`, `MT5_*` credentials) but is
   not part of the first release.

### 4.5 Vercel — frontend SPA

**BLOCKED-ON-OWNER:** `VERCEL_TOKEN` for scripted deploys and the owner's production domain.

1. **Import the repo** into Vercel; **Root Directory = `frontend`**; framework preset **Vite**;
   build command `npm run build` (`tsc -b && vite build`); output directory `dist`.
2. **SPA routing:** the app uses client-side routes (`/login`, `/register`, `/dashboard`, signal
   dashboard). Vercel must rewrite unknown paths to `/index.html`, otherwise a page refresh 404s.
   Add to the Vercel project (or as `frontend/vercel.json`):

   ```json
   { "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
   ```

   `frontend/nginx.conf` already does the equivalent (`try_files … /index.html`) for the self-hosted
   path.
3. **Choose how the SPA reaches the API** (this determines the CORS story):
   - **Option A — same-origin (recommended):** proxy the API through the frontend origin so the
     browser never makes a cross-origin request. Add rewrites for `/api/:path*` and `/auth/:path*` to
     the Render URL **before** the catch-all rewrite above, and leave `VITE_API_URL` unset. Fewer
     moving parts, no CORS preflight, cookies/headers unchanged. Rewrite order matters: API rules
     first, `/index.html` last.
   - **Option B — direct cross-origin calls:** set **`VITE_API_URL=https://<render-service>.onrender.com`**
     at build time (it is baked in: `frontend/src/lib/api.ts` prefixes every request with
     `import.meta.env.VITE_API_URL`) *and* add the Vercel origin to the backend's `CORS_ORIGINS`
     JSON list. Changing `VITE_API_URL` requires a **rebuild** of the frontend, and changing
     `CORS_ORIGINS` requires a **backend restart**.
   - No trailing slash on `VITE_API_URL` (paths are concatenated as `${API_BASE}${endpoint}`).
4. **Domain:** attach the owner-chosen production domain (BLOCKED-ON-OWNER) and make sure the same
   origin is in `CORS_ORIGINS` if you use Option B.
5. **Redeploy after** any `VITE_API_URL` / rewrite change.

---

## 5. Build commands

Exact commands, as used by the deploy script and CI:

```bash
# Frontend (from repo root) — produces frontend/dist
cd frontend && npm ci && npm run build          # npm ci needs package-lock.json (present)

# Backend image (optional locally; Render builds it from backend/Dockerfile on push)
docker build -f backend/Dockerfile -t forexai-backend:$(git rev-parse --short HEAD) backend/

# Backend without Docker (local dry-run / migration-only host)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

The backend is pure Python — there is no compile step; "build" means installing
`backend/requirements.txt` and (for Docker) building the image. Never build with a
`backend/.env` file present unless you intend that file to be baked into the image.

---

## 6. Database migration step (`alembic upgrade head`)

Migrations are managed with Alembic from `backend/` (config `backend/alembic.ini`, env
`backend/alembic/env.py`). **Alembic reads the app's `DATABASE_URL`** — the async asyncpg DSN — and
reuses the application's engine; `DATABASE_URL_SYNC` is declared in settings for parity but is not
used by `alembic/env.py`.

```bash
cd backend
export DATABASE_URL="…"        # injected by the platform / sourced from the Secrets store
export DATABASE_URL_SYNC="…"
python -m alembic upgrade head      # idempotent: at head it is a no-op
python -m alembic current           # prints the applied revision for the record
```

Rules of engagement:

- Run migrations **before** the new backend revision starts serving traffic (Render pre-deploy
  command, or a manual step from a trusted host with the production DSN).
- The deploy must be **idempotent**: `upgrade head` when already at head does nothing. The staging
  rebuild relies on exactly this property.
- Always take a pre-migration snapshot first (§4 of `OPERATIONS.md`) — the repo currently has a
  **single** migration (`2b91be147303`, "initial schema"), so a downgrade past it drops every
  application table. See `OPERATIONS.md` §3 before you ever roll back.
- Schema is owned by migrations in production. `create_all` is retained for dev/test only.

---

## 7. Startup order

Dependencies first, traffic last:

| # | Step | Wait for / verify | If it fails |
|---|---|---|---|
| 1 | Managed PostgreSQL reachable | `psql "$DATABASE_URL_SYNC" -c 'select 1'` | stop; backend cannot become ready (`/health/ready` → 503 `database: down`) |
| 2 | Managed Redis reachable | `redis-cli -u "$REDIS_URL" PING` → `PONG` | stop; readiness stays 503. (The API degrades gracefully at request level, but readiness must be honest — see the TLS gap in §4.2) |
| 3 | Migrations at head | `python -m alembic upgrade head`, then `alembic current` | stop; do not start the app against an unknown schema |
| 4 | Backend starts (Render) | `GET /health/live` → 200, then `GET /health/ready` → 200 `status: ok` | roll back the deploy; see `OPERATIONS.md` §7 |
| 5 | Market-data feed (if configured) | `GET /health/ready` → `components.market_data.status` | non-blocking: degraded is acceptable, mock fallback engages |
| 6 | Frontend deploys (Vercel) | `GET https://<domain>/` → 200; login + dashboard load | frontend is stateless — redeploy the previous build |
| 7 | CORS/domain verified | browser request to `/auth/login` from the real origin succeeds (no CORS error) | fix `CORS_ORIGINS` and restart the backend |

**Restart order for routine changes is Backend → Frontend** (the API must be serving before the SPA
that calls it); the full procedure and per-dependency awareness table are in `OPERATIONS.md` §5.

---

## 8. Health-check verification

Run these after every deploy (`scripts/deploy-prod.sh --verify --api-url …` automates them):

```bash
# 1. Liveness — process up, no dependencies touched
curl -sS "$PROD_API_URL/health/live"
# {"status":"ok","service":"forexai-terminal-backend","version":"0.2.0"}

# 2. Readiness — real PostgreSQL + Redis probes (503 when a core dependency is down)
curl -sS -o /tmp/ready.json -w 'HTTP %{http_code}\n' "$PROD_API_URL/health/ready"
# HTTP 200, body.status == "ok", components: api/database/redis ok, market_data ok|degraded, feed ok|degraded

# 3. Legacy alias (kept for the pre-observability contract)
curl -sS "$PROD_API_URL/health"        # {"status":"healthy",…}

# 4. In-process metrics (counters, latency percentiles, feed interruptions)
curl -sS "$PROD_API_URL/health/metrics"
curl -sS "$PROD_API_URL/health/metrics/prometheus"     # scrape target for monitoring

# 5. Auth + a real API read (proves the DB and JWT path end to end)
curl -sS -X POST "$PROD_API_URL/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"…","password":"…"}'                    # use a real account, not a literal in a script
```

Expected readiness payload (shape captured from the verified staging run):

```json
{"status":"ok","service":"forexai-terminal-backend","version":"0.2.0",
 "components":{"api":{"status":"ok"},"database":{"status":"ok"},
               "redis":{"status":"ok"},"market_data":{"status":"ok"},
               "feed":{"status":"ok","feed_interruptions":0}}}
```

Interpretation:

| Symptom | Meaning | Action |
|---|---|---|
| `/health/live` 200, `/health/ready` 503 | core dependency down (API/database/redis) | triage DB then Redis (`OPERATIONS.md` §7) |
| `/health/ready` 200 with `market_data: degraded` | feed problem only — by design not fatal | check broker credentials/quota; mock fallback is active |
| `/health/ready` 503 with `redis: down` on a `rediss://` DSN | readiness probe TLS gap (§4.2) | apply the code fix in `OPERATIONS.md` §8 |
| `/health/metrics` shows rising `api_errors_5xx` / `auth_failures` | application-level problem, not infrastructure | §7 incident runbook |

---

## 9. One-command deploy (`scripts/deploy-prod.sh`)

The script turns this document into executable steps and is safe to run by hand: it **never** prompts
for or prints a credential, reads everything from the environment, and does nothing destructive by
default.

```bash
# 1. Preflight only — validate the environment, change nothing
scripts/deploy-prod.sh --preflight

# 2. Validate + verify an already-running deployment (health-wait loop, then smoke checks)
scripts/deploy-prod.sh --verify --api-url "$PROD_API_URL" --fe-url "$PROD_FE_URL"

# 3. Full deploy: preflight → frontend build → migration → provider deploys → health-wait
APP_ENV=production … scripts/deploy-prod.sh --build-fe --migrate --deploy --api-url "$PROD_API_URL"
```

Flags: `--preflight`, `--build-fe`, `--build-be`, `--migrate`, `--deploy`, `--verify`, `--api-url URL`,
`--fe-url URL`, `--timeout SECONDS` (default 180), `--allow-local-deps` (loopback DB/Redis and
http origins permitted — **local dry-runs only**), `--yes` (skip the confirmation prompt for
destructive-ish steps). Exit codes: `0` ok, `1` failure, `2` usage error, `3` blocked on a missing
owner credential.

Local rehearsal that is genuinely useful without production credentials:

```bash
# Fails fast, lists missing variable names — the fail-mode proof
env -i PATH="$PATH" bash scripts/deploy-prod.sh --preflight

# Verifies a running (staging) backend over HTTP without touching production
scripts/deploy-prod.sh --verify --api-url http://127.0.0.1:8013 --timeout 30
```

If a deploy step fails, the script stops immediately, prints the failing step, the last health JSON it
saw, and the rollback command to run next — it never leaves you guessing which stage broke.

---

## 10. Post-deploy verification checklist

Run after the first production deploy and after every later deploy:

- [ ] `GET /health/live` → 200; `GET /health/ready` → 200 `status: ok` (all core components `ok`)
- [ ] `GET /health/metrics` reachable; `/health/metrics/prometheus` returns Prometheus text
- [ ] Register → login → `GET /api/v1/symbols` returns the 10 supported symbols
- [ ] `GET /api/v1/price/EURUSD` returns a bid/ask; candles `H1` return rows
- [ ] Indicators `H1` and SMC `H1` populate (backfill after warm-up; staging needed a poll loop)
- [ ] AI recommendation endpoint returns BUY/SELL/WAIT with reasoning + confidence
- [ ] Risk calculator returns position sizing for a sample account
- [ ] Backtest endpoint completes on a small range
- [ ] Frontend: login, dashboard widgets, signal dashboard load from the real origin with **no CORS
      error and a clean browser console**
- [ ] `CORS_ORIGINS` contains only the production HTTPS origin(s) — no staging origin, no `*`
- [ ] Production `JWT_SECRET` ≠ staging secret, length ≥ 32 (compare fingerprints, never values)
- [ ] Platform logs show no secret values and no startup guard error
- [ ] Rollback path rehearsed: previous Render revision and previous Vercel deployment are reachable

---

## 11. Rollback

Short form — the full decision rules and procedures are in [`OPERATIONS.md`](OPERATIONS.md) §3 and §7:

| Layer | Rollback |
|---|---|
| Backend | Render → redeploy the previous successful deploy (instant, stateless) |
| Frontend | Vercel → promote the previous deployment |
| Database | migrations are **forward-mostly**: prefer a forward fix. A downgrade across the initial schema **drops all tables** — snapshot first, and see `OPERATIONS.md` §3 |
| Secrets | restore the previous value in the provider Secrets store and restart the backend |

Helper: `scripts/rollback-prod.sh` prints the exact commands (dry-run by default) and, with
`--confirm`, performs the migration downgrade after a backup check.

---

## 12. Blocked-on-owner summary

| # | Blocked item | Exact credential/config names needed | Blocks |
|---|---|---|---|
| 1 | Tiger Cloud account + service | `TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID` (→ `DATABASE_URL`) | §4.1, §6, all data paths |
| 2 | Upstash account + database | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` (→ `REDIS_URL`) | §4.2, readiness 200 |
| 3 | Render account + service | `RENDER_API_KEY` (+ `RENDER_SERVICE_ID`) | §4.3, backend hosting |
| 4 | Vercel account + project | `VERCEL_TOKEN` | §4.5, frontend hosting |
| 5 | Broker REST **demo** credentials | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID` | real prices; mock works until then |
| 6 | Production domain / CORS origin decision | — (decision, then `CORS_ORIGINS`) | §4.5 step 4, HTTPS + CORS |
| 7 | Production `JWT_SECRET` value | `JWT_SECRET` | startup guard blocks the app without it |

Nothing in this pack requires a credential to be typed into a file or a script — all values arrive via
the platform's Secrets store and the process environment.
