#!/usr/bin/env bash
# =============================================================================
# ForexAI Terminal — self-test for the production deploy scripts (local only)
#
# Exercises scripts/deploy-prod.sh and scripts/rollback-prod.sh against synthetic
# environments and — when a local staging backend is running — the real staging
# stack on 127.0.0.1:8013. It NEVER touches production: no managed service is
# called and no credential is required. Safe to run any time.
#
# Usage:  bash scripts/deploy-prod-selftest.sh
# Output: every case is printed with its exit code; the summary shows pass/fail
#         per case. Exit 0 only when every case behaves as expected (a SKIP means
#         the optional local dependency was unavailable — it is not a failure).
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT="$(mktemp /tmp/deploy-prod-selftest.XXXXXX)"
# Every case runs in its own subshell (each needs a different environment), so a
# counter incremented inside one would be discarded when it exits. Record each
# outcome in a file and tally at the end — otherwise the summary always reads
# "0 passed, 0 failed" and the script can never exit non-zero.
RESULTS="$(mktemp /tmp/deploy-prod-selftest-results.XXXXXX)"
STAGING_ENV="${STAGING_ENV:-/tmp/staging_env.sh}"
STAGING_BE_URL="${STAGING_BE_URL:-http://127.0.0.1:8013}"
VENV_PYTHON="${PYTHON_BIN:-/opt/forexai-venv/bin/python}"

c_grn=$'\033[1;32m'; c_red=$'\033[1;31m'; c_reset=$'\033[0m'

clear_prod_env() {
  unset APP_ENV DATABASE_URL DATABASE_URL_SYNC REDIS_URL JWT_SECRET CORS_ORIGINS MARKET_DATA_PROVIDER \
        OANDA_API_KEY OANDA_ACCOUNT_ID OANDA_ENV MT5_LOGIN MT5_PASSWORD MT5_SERVER \
        STAGING_JWT_SECRET STAGING_DB_PASSWORD STAGING_REDIS_PASSWORD VERCEL_TOKEN RENDER_API_KEY RENDER_SERVICE_ID
}

# expect <expected-exit> <label> <command...>
expect() {
  local want="$1" label="$2"; shift 2
  "$@" >"$OUT" 2>&1
  local rc=$?
  if [ "$rc" = "$want" ]; then
    printf 'PASS\n' >>"$RESULTS"
    printf '  %sPASS%s [exit %s] %s\n' "$c_grn" "$c_reset" "$rc" "$label"
  else
    printf 'FAIL\n' >>"$RESULTS"
    printf '  %sFAIL%s [exit %s, wanted %s] %s\n' "$c_red" "$c_reset" "$rc" "$want" "$label"
    sed 's/\x1b\[[0-9;]*m//g' "$OUT" | sed 's/^/        /' | tail -20
  fi
}

printf '\nForexAI — deploy script self-test (local, no production contact)\n'

# ── Case 1: empty environment must fail ───────────────────────────────────────
(
  clear_prod_env
  expect 1 "empty env → preflight fails, lists missing variables" \
    env -i PATH="$PATH" bash scripts/deploy-prod.sh --preflight
)

# ── Case 2: production-shaped environment must pass ───────────────────────────
(
  clear_prod_env
  export APP_ENV=production
  export DATABASE_URL='postgresql+asyncpg://tsdbadmin:placeholder@db.example.tiger.cloud:30407/forexai?ssl=require'
  export DATABASE_URL_SYNC='postgresql://tsdbadmin:placeholder@db.example.tiger.cloud:30407/forexai?sslmode=require'
  export REDIS_URL='rediss://default:placeholder@example.upstash.io:6379/0'
  export JWT_SECRET="$(openssl rand -hex 32)"
  export CORS_ORIGINS='["https://app.forexai.example"]'
  export MARKET_DATA_PROVIDER=auto
  export OANDA_API_KEY=placeholder OANDA_ACCOUNT_ID=placeholder
  expect 0 "prod-shaped env (TLS DSN, https origin, broker creds) → preflight passes" \
    bash scripts/deploy-prod.sh --preflight
)

# ── Case 3: the asyncpg sslmode trap must be rejected ─────────────────────────
(
  clear_prod_env
  export APP_ENV=production
  export DATABASE_URL='postgresql+asyncpg://u:p@db.example.com:5432/db?sslmode=require'
  export DATABASE_URL_SYNC='postgresql://u:p@db.example.com:5432/db?sslmode=require'
  export REDIS_URL='rediss://default:p@example.upstash.io:6379/0'
  export JWT_SECRET="$(openssl rand -hex 32)"
  export CORS_ORIGINS='["https://app.example.com"]'
  export MARKET_DATA_PROVIDER=mock
  expect 1 "sslmode= in the asyncpg DSN → rejected with the ?ssl=require fix" \
    bash scripts/deploy-prod.sh --preflight
)

# ── Case 4: silent mock fallback must be rejected ─────────────────────────────
(
  clear_prod_env
  export APP_ENV=production
  export DATABASE_URL='postgresql+asyncpg://u:p@db.example.com:5432/db?ssl=require'
  export DATABASE_URL_SYNC='postgresql://u:p@db.example.com:5432/db?sslmode=require'
  export REDIS_URL='rediss://default:p@example.upstash.io:6379/0'
  export JWT_SECRET="$(openssl rand -hex 32)"
  export CORS_ORIGINS='["https://app.example.com"]'
  export MARKET_DATA_PROVIDER=oanda
  expect 1 "MARKET_DATA_PROVIDER=oanda without credentials → rejected" \
    bash scripts/deploy-prod.sh --preflight
)

# ── Case 5: insecure configuration and staging leakage must be rejected ───────
(
  clear_prod_env
  export APP_ENV=production
  export DATABASE_URL='postgresql+asyncpg://u:p@db.example.com:5432/forexai_staging?ssl=require'
  export REDIS_URL='redis://127.0.0.1:6379/0'
  export JWT_SECRET='dev-secret-key-change-in-production'
  export CORS_ORIGINS='["*"]'
  export MARKET_DATA_PROVIDER=mock
  export STAGING_JWT_SECRET=placeholder
  expect 1 "wildcard CORS + placeholder JWT + staging vars + staging DB → rejected" \
    bash scripts/deploy-prod.sh --preflight
)

# ── Case 6/7: health-wait loop (needs the local staging backend) ──────────────
if curl -sf -m 5 -o /dev/null "$STAGING_BE_URL/health/live"; then
  expect 0 "health-wait against the running local backend ($STAGING_BE_URL)" \
    bash scripts/deploy-prod.sh --verify --api-url "$STAGING_BE_URL" --timeout 20
else
  printf 'SKIP\n' >>"$RESULTS"
  printf '  SKIP health-wait success case — nothing listening on %s (start the staging stack to run it)\n' "$STAGING_BE_URL"
fi
(
  clear_prod_env
  expect 1 "health-wait timeout against a closed port → failure + rollback hint" \
    bash scripts/deploy-prod.sh --verify --api-url http://127.0.0.1:9 --timeout 4
)

# ── Case 8: rollback helper dry-run (read-only) ───────────────────────────────
if [ -f "$STAGING_ENV" ] && [ -x "$VENV_PYTHON" ]; then
  (
    clear_prod_env
    set -a; . "$STAGING_ENV"; set +a
    export PYTHON_BIN="$VENV_PYTHON"
    expect 0 "rollback-prod.sh --dry-run against a reachable database (no changes)" \
      bash scripts/rollback-prod.sh --dry-run
  )
else
  printf 'SKIP\n' >>"$RESULTS"
  printf '  SKIP rollback dry-run — %s or %s not available\n' "$STAGING_ENV" "$VENV_PYTHON"
fi

# ── Case 9/10: usage errors ───────────────────────────────────────────────────
(
  clear_prod_env
  expect 2 "unknown flag → usage error" bash scripts/deploy-prod.sh --nope
)
(
  clear_prod_env
  expect 2 "rollback without DATABASE_URL → usage error" bash scripts/rollback-prod.sh --dry-run
)

# Tally from the results file (the per-case subshells cannot update variables).
count() { grep -c "^$1$" "$RESULTS" 2>/dev/null || true; }
PASS="$(count PASS)"; FAIL="$(count FAIL)"; SKIPPED="$(count SKIP)"
printf '\nsummary: %s%s passed%s, %s%s failed%s, %s skipped\n' \
  "$c_grn" "$PASS" "$c_reset" \
  "$([ "$FAIL" -gt 0 ] && printf '%s' "$c_red" || printf '%s' "$c_grn")" "$FAIL" "$c_reset" "$SKIPPED"
rm -f "$OUT" "$RESULTS"
[ "$FAIL" -eq 0 ] || exit 1
