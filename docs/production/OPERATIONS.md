# ForexAI Terminal — Operations Manual

Status: **prepared, not executed** (no production deployment yet). Companion to
[`DEPLOYMENT.md`](DEPLOYMENT.md) (build/deploy) and [`ENV.md`](ENV.md) (configuration). Procedure
names, paths and environment-variable names are exact; **no secret values appear in this document**.

## TOC

1. [Topology and responsibilities](#1-topology-and-responsibilities)
2. [Command quick reference](#2-command-quick-reference)
3. [Migrations: run, verify, rollback](#3-migrations-run-verify-rollback)
4. [Backup and restore](#4-backup-and-restore)
5. [Restart procedure](#5-restart-procedure)
6. [Log collection, retention and rotation](#6-log-collection-retention-and-rotation)
7. [Incident-response runbook](#7-incident-response-runbook)
8. [Known gaps and required pre-production fixes](#8-known-gaps-and-required-pre-production-fixes)
9. [Owner actions and escalation](#9-owner-actions-and-escalation)

---

## 1. Topology and responsibilities

| Layer | Managed by | State | Restart impact |
|---|---|---|---|
| Frontend | Vercel (static build of `frontend/dist`) | none (stateless) | zero data risk |
| Backend API | Render container (`backend/Dockerfile`, `uvicorn app.main:app`) | in-process metrics + in-memory rate-limit counters only | counters reset; no data loss |
| Database | Tiger Cloud PostgreSQL | **all business data** | highest impact — never restart for convenience |
| Cache | Upstash Redis | disposable cache (short TTLs) | no data loss by design — the app degrades gracefully |
| Market data | broker REST demo feed behind `MarketDataProvider` | none | degraded output; mock fallback engages |

The backend holds no durable local state: everything that survives a restart lives in PostgreSQL. An
Redis outage degrades performance (cache misses) and makes `/health/ready` report `redis: down`, but
does not break request handling — `app/services/cache.py` swallows Redis errors by design.

Local staging (this machine) is a **separate environment**: PostgreSQL 16 + Redis 7 on loopback,
backend on `127.0.0.1:8013`, static+proxy frontend on `127.0.0.1:8081`, driven by
`/tmp/staging_env.sh` (mode 600) and `/home/team/shared/.staging-secrets`. It is never a production
backup target and production DSNs must never be pointed at it.

---

## 2. Command quick reference

```bash
# Validate a production environment without changing anything
scripts/deploy-prod.sh --preflight

# Verify a running deployment (health-wait loop + smoke checks)
scripts/deploy-prod.sh --verify --api-url "$PROD_API_URL" --fe-url "$PROD_FE_URL"

# Full deploy: preflight → FE build → migrate → provider deploys → health-wait
scripts/deploy-prod.sh --build-fe --migrate --deploy --api-url "$PROD_API_URL"

# Migration state
cd backend && python -m alembic current && python -m alembic heads && python -m alembic history

# Health
curl -sS "$PROD_API_URL/health/live" ; curl -sS -o /dev/null -w '%{http_code}\n' "$PROD_API_URL/health/ready"
curl -sS "$PROD_API_URL/health/metrics" ; curl -sS "$PROD_API_URL/health/metrics/prometheus"

# Backend logs (Render)
#   Dashboard → the service → Logs, or the Render CLI / API log stream
```

---

## 3. Migrations: run, verify, rollback

Alembic lives in `backend/`; `alembic/env.py` reuses the app's async engine and **`DATABASE_URL`**
(`DATABASE_URL_SYNC` is declared in settings but is not read by Alembic — do not assume a sync
migration path). Migrations are applied on every deploy (§6 of `DEPLOYMENT.md`).

### 3.1 Run

```bash
cd backend
export DATABASE_URL='postgresql+asyncpg://…?ssl=require'      # from the Secrets store, never literal
python -m alembic upgrade head
python -m alembic current        # record the revision in the deploy notes
```

### 3.2 Verify

```bash
cd backend
python -m alembic current        # applied revision, e.g. 2b91be147303 (head)
python -m alembic heads          # should match; more than one head = a branching mistake, stop
python -m alembic check          # optional: reports model/DDL drift (0 diffs is the healthy state)
psql "$DATABASE_URL_SYNC" -c 'select version_num from alembic_version;'
```

A deploy is healthy when `current` == `heads` and the application imports (the app also refuses to
start in production without a valid `JWT_SECRET` and explicit `CORS_ORIGINS`).

### 3.3 Rollback

> **Data-loss warning.** The repository contains **one** migration (`2b91be147303`, "initial
> schema"). Downgrading past it (`alembic downgrade base`) **drops every application table**, and
> `downgrade -1` from head *is* the initial migration's downgrade. There is no shrinking step
> available yet. Unless you have just taken and verified a snapshot (§4), treat any database
> downgrade as destroy-and-restore.

```bash
# 0. Snapshot first — always (see §4.1)
# 1. Inspect where you are and what a downgrade would run
cd backend && python -m alembic current && python -m alembic history -r -3:
# 2. Dry-run the SQL that the downgrade would execute (no connection writes)
python -m alembic downgrade -1 --sql | less
# 3. Apply, only with the shrink reviewed
python -m alembic downgrade -1
python -m alembic current        # confirm the new revision
curl -sS -o /dev/null -w '%{http_code}\n' "$PROD_API_URL/health/ready"   # 200 after rollback
```

`scripts/rollback-prod.sh` wraps this: **dry-run by default**, `--confirm` to execute,
`--backup-first` to force a snapshot, and it refuses to run while it cannot determine the current
revision. Roll back the application (Render/Vercel) **before** downgrading the database if the new
code expects the new schema.

### 3.4 Decision rules

| Situation | Action |
|---|---|
| New code bad, schema unchanged | roll back the app revision only (Render redeploy) — no DB action |
| Migration applied cleanly but app is bad | roll back app; leave the schema at head (usually backward compatible), fix forward |
| Migration failed **mid-way** | do **not** re-run blindly: inspect `alembic_version` + table state, then repair forward or restore from snapshot |
| Migration dropped/renamed data you need | restore the snapshot to a **scratch** database first, extract the rows, merge forward |
| Unsure | stop, snapshot, and treat it as an incident (§7) |

---

## 4. Backup and restore

### 4.1 Backup

Two layers, use both:

1. **Provider automated backups** (Tiger Cloud): confirm the retention window on the production
   service, and record where restores are triggered. This is the primary recovery path. **BLOCKED-ON-OWNER**
   until the Tiger service exists (`TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID`).
2. **Logical snapshots** before every migration and before any risky DB operation, taken with the
   libpq-style DSN (`DATABASE_URL_SYNC`, which accepts `sslmode`) — the asyncpg `DATABASE_URL` is for
   the application, `pg_dump` needs the sync form:

```bash
# pg_dump client version must be >= the server version (PG 16)
snap="/tmp/forexai-prod-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump "$DATABASE_URL_SYNC" --format=custom --no-owner --no-privileges --file="$snap"
ls -l "$snap"                      # non-trivial size, not 0 bytes
pg_restore --list "$snap" | head   # table of contents is readable
```

Never copy a snapshot to a place the repo can see, never commit it, and keep credentials out of it
(`--no-owner --no-privileges`).

### 4.2 Verify a backup (do this, not just the dump)

```bash
# Restore into a scratch database with the same PG major version, then compare
psql "$SCRATCH_DATABASE_URL" -c \
 "select table_name, (xpath('/row/c/text()',
   query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name),
                false, true, '')))[1]::text::int as rows
  from information_schema.tables where table_schema='public' order by 1;"
psql "$SCRATCH_DATABASE_URL" -c 'select version_num from alembic_version;'   # matches head
psql "$SCRATCH_DATABASE_URL" -c 'select count(*) from symbols;'              # 10 supported symbols
```

A backup is only "good" once restored and spot-checked. The staging analog of this discipline is the
team's idempotent rebuild script, which re-seeds and re-verifies the whole local stack in one command.

### 4.3 Restore

```bash
# 1. Announce the incident and freeze writes (stop the backend so it cannot write mid-restore)
# 2. Restore into a scratch DB first, verify (§4.2)
createdb_target="$SCRATCH_DATABASE_URL"
pg_restore --no-owner --no-privileges --dbname="$SCRATCH_DATABASE_URL" /tmp/forexai-prod-….dump
# 3. Only when verified, restore over production (point-of-no-return)
pg_restore --clean --if-exists --no-owner --no-privileges \
           --dbname="$DATABASE_URL_SYNC" /tmp/forexai-prod-….dump
# 4. Re-apply migrations to head (in case the dump predates the current revision)
cd backend && python -m alembic upgrade head
# 5. Restart the backend, then verify /health/ready == 200 and run the smoke checklist
```

Restoring over production discards everything written after the snapshot: capture the *current*
state first (`pg_dump` of the pre-restore DB) so the divergence can be reconciled afterwards.

### 4.4 Redis persistence notes

- Upstash (production): replication/durability is the provider's responsibility; the data stored by
  this app is **cache only** (short TTLs, default 30 s, `REDIS_CACHE_ENABLED` / `REDIS_CACHE_TTL_S`),
  so losing a Redis instance costs a cold cache, not correctness.
- Self-hosted (staging / VM): the staging config enables AOF (`appendonly yes`, `dir /var/lib/redis`)
  with `requirepass`; a flush is recoverable by restart alone.
- **Do not** store anything durable in Redis: in-memory rate-limit counters are per-process and
  intentionally non-durable (`app/utils/ratelimit.py`), and nothing else persists there.
- Restore drill: `redis-cli -u "$REDIS_URL" FLUSHDB` is safe in a non-production environment and is a
  valid way to prove the app degrades gracefully — check `/health/ready` returns and requests still
  succeed.

---

## 5. Restart procedure

Dependencies first, dependents last; verify after every step instead of at the end.

| Order | Step | Verify |
|---|---|---|
| 0 | Confirm PostgreSQL and Redis are healthy (managed: no restart needed) | `psql "$DATABASE_URL_SYNC" -c 'select 1'`; `redis-cli -u "$REDIS_URL" PING` |
| 1 | **Backend** (Render: Restart / Redeploy) | `GET /health/live` 200 → `GET /health/ready` 200 `status: ok` |
| 2 | **Frontend** (Vercel: only needed if a new build was published) | `GET https://<domain>/` 200, login + dashboard load, no console errors |
| 3 | Post-restart smoke | checklist §10 of `DEPLOYMENT.md` |

Why this order: the SPA calls `/auth/*` and `/api/v1/*` on load; restarting the backend while the
frontend is live causes user-visible errors only for the restart window, whereas publishing a new
frontend first can point users at API behaviour that is not deployed yet.

Dependency awareness:

| Change | Blast radius | Notes |
|---|---|---|
| `JWT_SECRET` | **all sessions invalidated** | users must log in again; schedule, don't surprise them |
| `CORS_ORIGINS` | browsers blocked from the API | requires a backend restart to take effect |
| `DATABASE_URL` / `REDIS_URL` | full outage if wrong | preflight the DSN (and `ssl=require`, never `sslmode` for the async URL) |
| `MARKET_DATA_PROVIDER` | analysis quality only | mock fallback keeps the API up |
| Rate-limit constants (`AUTH_*`) | login/register throttling | restart resets counters |
| Frontend `VITE_API_URL` | API unreachable from the browser | **build-time** value: needs a new Vercel build, not just a restart |

The backend has no zero-downtime guarantee on a single instance: a Render restart is a short outage.
Create the new revision and restart during a low-usage window, and use `/health/ready` as the signal
that the new revision is actually serving.

---

## 6. Log collection, retention and rotation

**What the app emits.** `app/utils/logging_config.py` configures a single `StreamHandler` on stdout
with `%Y-%m-%d %H:%M:%S [LEVEL] logger.name: message` at INFO by default; SQLAlchemy engine logging is
silenced to WARNING. So:

- **Render:** stdout/stderr are captured automatically and streamed in the dashboard's Logs tab
  (retention follows the plan). Keep the platform stream as the primary source of truth; no log files
  are written inside the container.
- **Vercel:** build logs plus runtime/function logs for the static deployment (and any rewrites).
- **Tiger Cloud / Upstash:** provider dashboards for slow queries, connections, errors and metrics.

**Rotation for self-hosted deployments** (VM / staging-like, where the process is started with
`setsid nohup … >> /tmp/…log`): rotate with a `logrotate` rule rather than truncating an open file:

```
# /etc/logrotate.d/forexai
/var/log/forexai/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

Guidance: keep ≥ 14 days of application logs and ≥ 90 days of deploy/incident records; the staging
machine's logs (`/tmp/staging_uvicorn.log`, `/tmp/staging_fe.log`) are ephemeral and are wiped on
rebuild — never treat them as an audit trail.

**What to capture during an incident** (before restarting anything that would lose it): the failing
health JSON, the ±10 minutes of logs around the first error, the deploy/revision ID, request IDs if
present, and `/health/metrics` snapshots. In-process metrics live only in memory, so a restart
destroys the evidence.

**Secret hygiene in logs.** The app never logs credentials or DSNs, and the readiness payload is
explicitly secret-free (covered by a unit test). Still, before sharing logs externally:

```bash
grep -Ei 'password|jwt|secret|api[_-]?key|authorization|bearer|postgres(ql)?://|rediss?://' <logfile>
```

If this matches, redact before sharing. Never paste a connection string into a chat, ticket or doc.

**Monitoring hooks.** `/health/metrics/prometheus` is the scrape target (counters for requests, 4xx,
5xx, auth failures, feed interruptions/recoveries, latency avg/p95, uptime). Point an external monitor
at `/health/live` (liveness), `/health/ready` (readiness) and that endpoint; alerting is not yet
configured (§8 item 4).

---

## 7. Incident-response runbook

### 7.1 Severity

| Level | Trigger | Response target |
|---|---|---|
| **S1** | API unavailable, database unreachable/corrupt, all logins failing, suspected credential exposure | act immediately, all hands; owner informed |
| **S2** | Partial degradation: readiness 503 on one dependency, elevated 5xx, feed interruptions, latency spike | start triage within 15 min |
| **S3** | Cosmetic/analysis-quality issues, single-user problems, elevated 4xx from bad input | normal working hours |

### 7.2 Detect

Signals available today (in-process, no external monitoring configured yet):

- `GET /health/live` — process up (200 expected; non-200/timeout = S1).
- `GET /health/ready` — 200 only when API + PostgreSQL + Redis are all `ok`; 503 names the broken
  component in `components.*`. `market_data: degraded` alone is not a core failure.
- `GET /health/metrics` — `requests_total`, `api_errors_4xx`, `api_errors_5xx`, `auth_failures`,
  `feed_interruptions`, `feed_recoveries`, `latency.avg_ms`/`p95_ms`/`samples`, `uptime_seconds`.
- `GET /health/metrics/prometheus` — same counters for scraping.
- Platform signals: Render deploy/restart events and container logs, Vercel deployment failures,
  provider (Tiger/Upstash) status + connection metrics.
- User reports (login fails, prices frozen) — still the most likely first signal until alerting exists.

### 7.3 Triage checklist (first 5 minutes)

1. Scope it: `/health/live` and `/health/ready` — is the process up, and which component is named?
2. Time-correlate: did it start at a deploy? check Render/Vercel deploy history for the same minute.
3. **Freeze changes**: no further deploys or migrations until the situation is understood.
4. Preserve evidence: snapshot the health JSONs, `/health/metrics`, and the last 10 minutes of logs
   (metrics are in-memory and die with a restart).
5. Classify severity (§7.1) and pick the decision rule (§7.4).
6. Act, then confirm with `/health/ready` + a real login + `GET /api/v1/symbols` (10 symbols).
7. Record a timeline as you go — it is the input to the post-incident review (§7.6).

### 7.4 Decision rules (rollback vs roll forward vs fail open)

| If… | Then |
|---|---|
| The incident started within ~30 min of a deploy and the previous revision was healthy | **Roll back the app first** (Render redeploy / Vercel promote). Fastest, lowest risk. Do **not** downgrade the DB unless the new code wrote an incompatible schema change |
| A migration just ran and the schema is suspect | stop traffic to the new revision, snapshot, inspect `alembic_version`; restore to a scratch DB to compare before touching production |
| Only the market-data feed is broken | **Fail open**: keep serving; confirm the mock fallback is active; the API must stay 200 |
| Only Redis is down (cache) | keep serving (graceful degradation) and fix Redis; expect `/health/ready` 503 — see the TLS gap (§8.1) if the DSN is `rediss://` |
| Authentication or a security control is failing | **Fail closed**: block the affected path, rotate the secret, invalidate sessions; never "temporarily fix" auth |
| Data may be corrupted | stop writes immediately, snapshot the current state, then restore per §4.3 |
| Cause unknown and impact is contained | prefer a careful forward fix over a blind rollback; keep the evidence |

### 7.5 Scenario playbooks

- **API 5xx / down (S1).** `/health/live` failing → the process is gone (check Render for restart
  loops, OOM, or a startup crash). Common startup crashes: the production guard rejecting
  `JWT_SECRET` (missing/placeholder/<32 chars) or an invalid `CORS_ORIGINS` — the log line names it.
  Live but 5xx → `/health/ready` names the dependency; continue below. If readiness is 200 but
  errors are rising, use `/health/metrics` and logs to find the offending endpoint, then decide
  rollback vs fix.
- **Database unreachable / saturated (S1/S2).** Verify with `psql "$DATABASE_URL_SYNC" -c 'select 1'`.
  Check the async DSN has `ssl=require` (never `sslmode`, §8.9), connection-limit/pool exhaustion
  (`pool_size=20`, `max_overflow=10` per instance) and provider status. A wrong DSN after a secret
  rotation is the most common self-inflicted cause.
- **Redis down / readiness 503 (S2).** `redis-cli -u "$REDIS_URL" PING`. If the DSN is `rediss://`,
  apply the fix in §8.1 before concluding Redis is broken. Cache loss is harmless; do not restore a
  cache.
- **Market-data feed interrupted (S2/S3).** `components.market_data` + `feed_interruptions` /
  `feed_recoveries` counters. Check broker demo credentials, quota and provider status. The app is
  designed to stay up; analysis output degrades to mock. Reconnection/backoff exists only for the MT5
  path — for REST providers, a restart re-establishes the feed.
- **Auth failure spike / brute force (S2).** `auth_failures` rising; per-IP and per-account sliding
  windows throttle register/login/refresh. Tighten `AUTH_*` limits (backend restart) and rotate
  credentials if an account is compromised. Remember the limiter is per-process (§8.2).
- **Migration failure during deploy (S1).** Application must be rolled back; inspect the failed
  revision, correct it, and re-run `upgrade head`. Never hand-edit `alembic_version`.
- **Data corruption / bad batch (S1).** Freeze writes, snapshot now, restore per §4.3 into a scratch
  DB first, reconcile the diff, then cut over and re-apply migrations to head.
- **Suspected secret exposure (S1, security).** Rotate the affected credential at the provider, update
  the Secrets store, restart the backend, confirm old sessions fail, and audit access logs. Rotating
  `JWT_SECRET` logs every user out — that is the intended behaviour, not a bug. Then search the logs
  (§6) for the leaked value to bound the exposure window.
- **Elevated latency (S2/S3).** `latency.p95_ms` climbing with stable infrastructure usually means a
  cold cache (after a Redis flush/restart), a slow DB query/provider call, or a single-instance CPU
  limit. Check Render CPU/memory, Tiger slow queries, and whether `REDIS_CACHE_ENABLED` is on.

### 7.6 Post-incident review (within 5 working days)

Record: **detection** (how it was noticed, how long it took), **impact** (duration, users, data
affected), **timeline**, **root cause**, **what went well / what hindered**, and **actions** with
owners and dates. Standard follow-ups: add the missing alert/monitor, add the missing test, tighten
the DSN/env preflight, and update this runbook. The mandatory check: could the deploy script's
preflight have caught this? If yes, add the check there (that is how `ssl` vs `sslmode` and the
`rediss://` warning got into this pack).

---

## 8. Known gaps and required pre-production fixes

These are honest, verified observations from the current code and the staging runs. Items 1–3 are
**code/infra follow-ups** that should block the first production deploy or be explicitly accepted.

1. **Readiness probe ignores TLS on `rediss://` (blocking for Upstash).**
   `app/services/health.py::check_redis` builds its client from `urlparse(REDIS_URL)` host/port/
   password/db **without** `ssl`, so a TLS DSN reports `redis: down`, `/health/ready` returns **503**,
   and a platform health check would restart-loop the service. The request path is unaffected
   (`app/services/cache.py` uses `redis.asyncio.from_url`, which understands `rediss://`), and the
   app itself keeps working; readiness is simply wrong. Fix: enable TLS for `rediss://` in
   `check_redis` (pass `ssl=True` / use `from_url`) plus a unit test; the deploy script warns until
   then. Until it is fixed, do not put a `rediss://` DSN behind a `healthCheckPath=/health/ready`.
2. **Rate limiting is per-process** (`app/utils/ratelimit.py`): limits are not shared across instances
   and reset on restart. Keep one backend instance, or move the limiter to Redis before scaling out.
3. **Metrics are in-process**: they reset on restart and are not aggregated across instances. Fine for
   a single instance; pair `/health/metrics/prometheus` with an external scraper for history.
4. **No alerting/monitoring configured yet** — someone must look at `/health` or hear from users. The
   observability work in the plan is in progress; at minimum add an external probe on `/health/live`,
   `/health/ready` and `/health/metrics/prometheus`.
5. **No automated smoke canary**: the post-deploy checklist in `DEPLOYMENT.md` §10 is manual.
6. **Single region, no read replica**: RTO depends on the providers' own restore times.
7. **`DATABASE_URL_SYNC` is unused by Alembic** (Alembic reuses the async `DATABASE_URL`) — keep both
   set, but do not assume a sync migration path exists.
8. **Default single uvicorn worker** (Dockerfile command): the in-process state above is per worker;
   note it before changing the worker count.
9. **`ssl` vs `sslmode` on the async DSN** (verified failure mode): `sslmode=require` in
   `DATABASE_URL` raises `TypeError: connect() got an unexpected keyword argument 'sslmode'` from
   asyncpg. Use `ssl=require`. `--preflight` rejects this.
10. **No real-money execution path, by design** — first release is live data + analysis + signal/paper
    only. Any change here is a product/risk decision, not an ops task.

Local staging-only notes (do not apply to production): the machine's apt mirror must point at
`http://azure.archive.ubuntu.com/ubuntu/` before any `apt` step, and the backend test suite needs a
separate database whose name contains `test` (`forexai_test`) to exercise the integration gate. The
verified full-suite run, environment restoration notes and reliable result-capture method are recorded
in `/home/team/shared/verification-observability-merged.md` — reference, do not rewrite.

---

## 9. Owner actions and escalation

| # | Owner action | Names / decision | Blocks |
|---|---|---|---|
| 1 | Create the managed PostgreSQL service | `TIGER_PUBLIC_KEY`, `TIGER_SECRET_KEY`, `TIGER_PROJECT_ID` | all data paths |
| 2 | Create the managed Redis database | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | readiness 200 |
| 3 | Create the backend service | `RENDER_API_KEY` (+ service id) | backend hosting |
| 4 | Create the frontend project | `VERCEL_TOKEN` | frontend hosting |
| 5 | Provide broker REST **demo** credentials | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID` | real prices (mock works meanwhile) |
| 6 | Choose the production domain / CORS origin | decision → `CORS_ORIGINS` | HTTPS, CORS, DNS |
| 7 | Approve the recurring cost of the four services | decision | anything with a bill |
| 8 | Approve the first-release safety scope (advisory only) | decision | any execution-related work |

Escalate to the owner (or the team lead) when an action needs a credential, a billing decision, a
domain change, or a data-restore approval. Everything else — restarts, log inspection, health
verification, migration on a healthy deploy, snapshot/verify — is within the operator's remit.
