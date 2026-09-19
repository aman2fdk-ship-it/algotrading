#!/usr/bin/env bash
# =============================================================================
# ForexAI Terminal — production deploy driver (safe to run by hand)
#
# Turns docs/production/DEPLOYMENT.md into executable steps:
#   preflight (env validation) -> build frontend -> build backend image ->
#   run migrations (alembic upgrade head) -> trigger provider deploys ->
#   health-wait loop with timeout -> smoke checks.
#
# Safe by default: with no action flags it only runs the preflight (no side
# effects, no network writes). It NEVER prompts for, prints or stores a
# credential — every value is read from the environment and DSNs are masked in
# all output. Nothing destructive happens without an explicit flag.
#
# Usage:
#   scripts/deploy-prod.sh --preflight
#   scripts/deploy-prod.sh --verify --api-url "$PROD_API_URL" [--fe-url "$PROD_FE_URL"]
#   scripts/deploy-prod.sh --build-fe --migrate --deploy --api-url "$PROD_API_URL"
#   scripts/deploy-prod.sh --all --api-url "$PROD_API_URL" --fe-url "$PROD_FE_URL"
#
# Exit codes: 0 = ok, 1 = failure, 2 = usage error, 3 = blocked on a missing
#             owner-provided credential (see docs/production/DEPLOYMENT.md §12).
#
# Required env for --preflight (names only; values live in the Secrets store):
#   APP_ENV DATABASE_URL DATABASE_URL_SYNC REDIS_URL JWT_SECRET CORS_ORIGINS
#   MARKET_DATA_PROVIDER
# Extra env per action:
#   --migrate   nothing new (uses DATABASE_URL)
#   --deploy    RENDER_API_KEY + RENDER_SERVICE_ID (backend), VERCEL_TOKEN (frontend)
#   --verify    nothing new (targets --api-url)
# =============================================================================
set -euo pipefail

SCRIPT_NAME="deploy-prod"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
DO_PREFLIGHT=0
DO_BUILD_FE=0
DO_BUILD_BE=0
DO_MIGRATE=0
DO_DEPLOY=0
DO_VERIFY=0
ALLOW_LOCAL=0
ASSUME_YES=0
API_URL="${PROD_API_URL:-}"
FE_URL="${PROD_FE_URL:-}"
TIMEOUT="${HEALTH_TIMEOUT_S:-180}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# ── Output helpers (never print a secret value) ───────────────────────────────
c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_red=$'\033[1;31m'; c_grn=$'\033[1;32m'
c_ylw=$'\033[1;33m'; c_cyn=$'\033[1;36m'
step() { printf '\n%s==> %s%s\n' "$c_cyn" "$*" "$c_reset"; }
ok()   { printf '  %sOK%s   %s\n' "$c_grn" "$c_reset" "$*"; }
warn() { printf '  %sWARN%s %s\n' "$c_ylw" "$c_reset" "$*"; }
bad()  { printf '  %sFAIL%s %s\n' "$c_red" "$c_reset" "$*"; PROBLEMS=$((PROBLEMS+1)); }
die()  { printf '\n%s%s: %s%s\n' "$c_red" "$SCRIPT_NAME" "$*" "$c_reset" >&2; exit "${2:-1}"; }

PROBLEMS=0

usage() { sed -n '3,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# mask a DSN so logs never show credentials: scheme://***@host:port/db
mask() { printf '%s' "$1" | sed -E 's#(://)[^@/]*@#\1***@#g'; }

have() { command -v "$1" >/dev/null 2>&1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --preflight|--dry-run) DO_PREFLIGHT=1 ;;
    --build-fe)  DO_BUILD_FE=1; DO_PREFLIGHT=1 ;;
    --build-be)  DO_BUILD_BE=1; DO_PREFLIGHT=1 ;;
    --migrate)   DO_MIGRATE=1;  DO_PREFLIGHT=1 ;;
    --deploy)    DO_DEPLOY=1;   DO_PREFLIGHT=1 ;;
    --verify)    DO_VERIFY=1 ;;
    --all)       DO_PREFLIGHT=1; DO_BUILD_FE=1; DO_BUILD_BE=1; DO_MIGRATE=1; DO_DEPLOY=1; DO_VERIFY=1 ;;
    --allow-local-deps) ALLOW_LOCAL=1 ;;
    --yes|-y)    ASSUME_YES=1 ;;
    --api-url)   API_URL="${2:-}"; shift ;;
    --fe-url)    FE_URL="${2:-}"; shift ;;
    --timeout)   TIMEOUT="${2:-}"; shift ;;
    -h|--help)   usage 0 ;;
    *) usage 2 ;;
  esac
  shift
done

if [ $((DO_PREFLIGHT+DO_VERIFY)) -eq 0 ]; then DO_PREFLIGHT=1; fi   # nothing asked for -> safe default

if [ "$ALLOW_LOCAL" = 1 ]; then
  printf '%s!! --allow-local-deps: loopback dependencies, http origins and missing TLS are accepted.\n' "$c_ylw"
  printf '   Local rehearsal ONLY. Never use this for a real production deploy.%s\n' "$c_reset"
fi

# ── Preflight ─────────────────────────────────────────────────────────────────
is_loopback() { case "$1" in *127.0.0.1*|*localhost*) return 0 ;; *) return 1 ;; esac; }

check_app_env() {
  local v="${APP_ENV:-}"
  case "$(printf '%s' "$v" | tr '[:upper:]' '[:lower:]')" in
    production|prod) ok "APP_ENV=$v (production security guard active)" ;;
    "") bad "APP_ENV is not set — production requires APP_ENV=production" ;;
    *)  bad "APP_ENV='$v' — production requires APP_ENV=production (got a non-production value)" ;;
  esac
}

check_jwt_secret() {
  local s="${JWT_SECRET:-}" len
  if [ -z "$s" ]; then bad "JWT_SECRET is not set (generate with: openssl rand -hex 32)"; return; fi
  if [ "$s" = "dev-secret-key-change-in-production" ]; then
    bad "JWT_SECRET is still the development placeholder — startup will fail in production"; return
  fi
  len="$(printf '%s' "$s" | wc -c | tr -d ' ')"
  if [ "$len" -lt 32 ]; then bad "JWT_SECRET is only $len characters — production requires >= 32"; return; fi
  ok "JWT_SECRET present, non-placeholder, length >= 32"
}

check_cors() {
  local v="${CORS_ORIGINS:-}" out
  if [ -z "$v" ]; then bad "CORS_ORIGINS is not set"; return; fi
  if ! have python3; then warn "python3 unavailable — CORS_ORIGINS checked with a crude test only"; return; fi
  if ! out="$(CORS_RAW="$v" python3 - <<'PY' 2>/dev/null
import json, os, sys
raw = os.environ["CORS_RAW"]
try:
    parsed = json.loads(raw)
except Exception as exc:                      # noqa: BLE001
    print("PARSE:%s" % exc); sys.exit(0)
if not isinstance(parsed, list) or not parsed:
    print("EMPTY"); sys.exit(0)
for o in parsed:
    if not isinstance(o, str): print("NONSTR"); sys.exit(0)
    if o.strip() == "*":       print("WILDCARD"); sys.exit(0)
    if o.strip() == "":        print("BLANK"); sys.exit(0)
print("OK")
for o in parsed:
    print("ORIGIN:%s" % o.strip().rstrip("/"))
PY
)"; then bad "CORS_ORIGINS could not be validated"; return; fi
  case "$out" in
    OK*) ;;
    WILDCARD) bad 'CORS_ORIGINS contains "*" — rejected (credentials are enabled)'; return ;;
    EMPTY)    bad "CORS_ORIGINS must be a non-empty JSON list of origins"; return ;;
    PARSE*)   bad "CORS_ORIGINS is not valid JSON (${out#PARSE:})"; return ;;
    *)        bad "CORS_ORIGINS is malformed ($out)"; return ;;
  esac
  local n=0 o
  while IFS= read -r line; do
    case "$line" in ORIGIN:*) o="${line#ORIGIN:}"; n=$((n+1))
      if is_loopback "$o"; then
        if [ "$ALLOW_LOCAL" = 1 ]; then warn "CORS_ORIGINS contains loopback origin '$o' (allowed locally)";
        else bad "CORS_ORIGINS contains loopback origin '$o' — production needs a public origin"; fi
      elif [ "${o#https://}" = "$o" ]; then
        if [ "$ALLOW_LOCAL" = 1 ]; then warn "CORS_ORIGINS origin '$o' is not https (allowed locally)";
        else bad "CORS_ORIGINS origin '$o' is not an https:// origin"; fi
      fi ;;
    esac
  done <<< "$out"
  ok "CORS_ORIGINS valid JSON allow-list ($n origin(s), no wildcard)"
}

check_database_url() {
  local u="${DATABASE_URL:-}" s="${DATABASE_URL_SYNC:-}"
  if [ -z "$u" ]; then bad "DATABASE_URL is not set"; return; fi
  case "$u" in
    postgresql+asyncpg://*) ;;
    postgresql://*) bad "DATABASE_URL must use the async driver: postgresql+asyncpg://… (got postgresql://…)" ;;
    *) bad "DATABASE_URL must start with postgresql+asyncpg:// (got: $(mask "${u%%/*//}"))" ;;
  esac
  case "$u" in
    *sslmode=*) bad "DATABASE_URL contains sslmode= — asyncpg rejects it (TypeError). Use ?ssl=require instead" ;;
  esac
  case "$u" in
    *channel_binding=*) bad "DATABASE_URL contains channel_binding= — asyncpg rejects it. Remove it" ;;
  esac
  local host="${u#*://}"; host="${host#*@}"; host="${host%%/*}"; host="${host%%:*}"
  if is_loopback "$host"; then
    if [ "$ALLOW_LOCAL" = 1 ]; then warn "DATABASE_URL points at loopback host '$host' (allowed locally)"
    else bad "DATABASE_URL points at loopback host '$host' — production must use the managed database"; fi
  fi
  case "$u" in
    *"[::"*) warn "DATABASE_URL host looks IPv6/IPv4-literal — verify the managed hostname" ;;
    *ssl=*) ;;
    *) if [ "$ALLOW_LOCAL" = 1 ]; then warn "DATABASE_URL has no ssl parameter (allowed locally)"
       else warn "DATABASE_URL has no ssl= parameter — managed PostgreSQL normally requires ?ssl=require"; fi ;;
  esac
  ok "DATABASE_URL shape valid: $(mask "$u")"
  if [ -z "$s" ]; then
    warn "DATABASE_URL_SYNC is not set — pg_dump/pg_restore/psql (libpq, sslmode=) need it (see OPERATIONS.md §4.1)"
  else
    case "$s" in
      postgresql://*) ok "DATABASE_URL_SYNC present (libpq form)" ;;
      *) warn "DATABASE_URL_SYNC should be postgresql://… (libpq form) for pg_dump/psql" ;;
    esac
  fi
}

check_redis_url() {
  local u="${REDIS_URL:-}"
  if [ -z "$u" ]; then bad "REDIS_URL is not set"; return; fi
  case "$u" in
    rediss://*) warn "REDIS_URL uses TLS (rediss://) — check_redis() cannot probe TLS yet, so /health/ready may return 503. See OPERATIONS.md §8.1 (code fix required)" ;;
    redis://*) ;;
    *) bad "REDIS_URL must start with redis:// or rediss://" ;;
  esac
  local host="${u#*://}"; host="${host#*@}"; host="${host%%/*}"; host="${host%%:*}"
  if is_loopback "$host"; then
    if [ "$ALLOW_LOCAL" = 1 ]; then warn "REDIS_URL points at loopback host '$host' (allowed locally)"
    else bad "REDIS_URL points at loopback host '$host' — production must use the managed Redis"; fi
  fi
  ok "REDIS_URL shape valid: $(mask "$u")"
}

check_market_data_provider() {
  local p="${MARKET_DATA_PROVIDER:-auto}"
  case "$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')" in
    auto)
      if [ -n "${OANDA_API_KEY:-}" ] && [ -n "${OANDA_ACCOUNT_ID:-}" ]; then
        ok "MARKET_DATA_PROVIDER=auto with broker REST credentials present"
      else
        warn "MARKET_DATA_PROVIDER=auto without broker credentials — will run on the MOCK feed (no live prices)"
      fi ;;
    oanda)
      if [ -n "${OANDA_API_KEY:-}" ] && [ -n "${OANDA_ACCOUNT_ID:-}" ]; then
        ok "MARKET_DATA_PROVIDER=oanda with credentials present (OANDA_ENV=${OANDA_ENV:-practice})"
      else
        bad "MARKET_DATA_PROVIDER=oanda but OANDA_API_KEY/OANDA_ACCOUNT_ID are unset — the app would silently fall back to mock. Set the credentials, or set MARKET_DATA_PROVIDER=mock to accept the fallback explicitly"
      fi ;;
    mt5)
      if [ -n "${MT5_LOGIN:-}" ] && [ -n "${MT5_PASSWORD:-}" ] && [ -n "${MT5_SERVER:-}" ]; then
        ok "MARKET_DATA_PROVIDER=mt5 with credentials present"
      else
        bad "MARKET_DATA_PROVIDER=mt5 but MT5_LOGIN/MT5_PASSWORD/MT5_SERVER are incomplete"
      fi ;;
    mock) ok "MARKET_DATA_PROVIDER=mock (explicit: advisory output based on synthetic data)" ;;
    *)    bad "MARKET_DATA_PROVIDER='$p' is not one of auto|oanda|mt5|mock (the app would fall back to mock)" ;;
  esac
}

check_separation() {
  local leaked=0 v
  for v in STAGING_JWT_SECRET STAGING_DB_PASSWORD STAGING_REDIS_PASSWORD; do
    if [ -n "${!v:-}" ]; then bad "staging variable $v is present in the production environment — staging and production must be fully separate"; leaked=1; fi
  done
  case "${DATABASE_URL:-}" in *forexai_staging*) bad "DATABASE_URL points at the staging database name"; leaked=1 ;; esac
  [ "$leaked" = 1 ] || ok "no staging-only variables or staging database name detected"
}

check_tooling() {
  have curl || bad "curl is required"
  if [ "$DO_BUILD_FE" = 1 ]; then have npm || bad "npm is required for --build-fe"; fi
  if [ "$DO_MIGRATE" = 1 ]; then
    have "$PYTHON_BIN" || bad "$PYTHON_BIN is required for --migrate (set PYTHON_BIN to override)"
    if [ ! -d "$REPO_ROOT/backend/alembic" ]; then bad "backend/alembic not found — run from the repository"; fi
  fi
  if [ "$DO_BUILD_BE" = 1 ]; then have docker || warn "docker not found — --build-be will print the Render build path instead"; fi
  ok "tooling check complete"
}

preflight() {
  step "preflight — environment validation (no changes made)"
  local v
  for v in APP_ENV DATABASE_URL REDIS_URL JWT_SECRET CORS_ORIGINS; do
    if [ -z "${!v:-}" ]; then bad "$v is not set"; fi
  done
  if [ -z "${MARKET_DATA_PROVIDER:-}" ]; then
    warn "MARKET_DATA_PROVIDER is not set — the app defaults to 'auto' (mock when no broker credentials exist)"
  fi
  check_app_env
  check_jwt_secret
  check_cors
  if [ -n "${DATABASE_URL:-}" ]; then check_database_url; fi
  if [ -n "${REDIS_URL:-}" ]; then check_redis_url; fi
  check_market_data_provider
  check_separation
  check_tooling

  if [ "$PROBLEMS" -gt 0 ]; then
    printf '\n%s%s: preflight FAILED with %d problem(s). Fix the items above before deploying.%s\n' \
      "$c_red" "$SCRIPT_NAME" "$PROBLEMS" "$c_reset" >&2
    exit 1
  fi
  ok "preflight passed — environment looks deployable"
}

# ── Build steps ───────────────────────────────────────────────────────────────
build_frontend() {
  step "build frontend (frontend/ -> dist/)"
  [ -d "$REPO_ROOT/frontend" ] || die "frontend/ not found" 1
  ( cd "$REPO_ROOT/frontend"
    if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
    npm run build )
  [ -f "$REPO_ROOT/frontend/dist/index.html" ] || die "frontend build produced no dist/index.html" 1
  ok "frontend build complete: frontend/dist/index.html present"
  if [ -n "${VITE_API_URL:-}" ]; then
    ok "VITE_API_URL was set at build time (value not printed)"
  else
    ok "VITE_API_URL unset — bundle uses same-origin API paths"
  fi
}

build_backend() {
  step "build backend image (backend/Dockerfile)"
  if have docker; then
    local tag="forexai-backend:$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
    docker build -f "$REPO_ROOT/backend/Dockerfile" -t "$tag" "$REPO_ROOT/backend"
    ok "image built: $tag"
  else
    warn "docker unavailable — skipping local image build"
    ok "Render builds backend/Dockerfile on push (see DEPLOYMENT.md §4.3)"
  fi
}

# ── Migration ─────────────────────────────────────────────────────────────────
run_migrations() {
  step "migrations — alembic upgrade head (backend/)"
  [ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL is required for --migrate" 1
  ok "target database: $(mask "$DATABASE_URL")"
  warn "take a snapshot first when the migration is not a no-op: OPERATIONS.md §4.1 (pg_dump with DATABASE_URL_SYNC)"
  if [ "$ASSUME_YES" != 1 ]; then
    printf '  Apply migrations to the database above? [y/N] '
    read -r reply
    case "$reply" in y|Y|yes|YES) ;; *) die "migration aborted by operator" 1 ;; esac
  fi
  ( cd "$REPO_ROOT/backend"
    "$PYTHON_BIN" -m alembic current || true
    "$PYTHON_BIN" -m alembic upgrade head
    "$PYTHON_BIN" -m alembic current )
  ok "migrations at head"
  ok "verify recorded revision with: cd backend && $PYTHON_BIN -m alembic current"
}

# ── Provider deploys ──────────────────────────────────────────────────────────
deploy_providers() {
  step "provider deploys"
  local blocked=0

  if [ "$DO_BUILD_FE" = 1 ] || [ "$DO_DEPLOY" = 1 ]; then
    if [ -n "${VERCEL_TOKEN:-}" ]; then
      if have npx; then
        ok "triggering Vercel production deploy (token read from env, never printed)"
        ( cd "$REPO_ROOT/frontend" && VERCEL_TOKEN="$VERCEL_TOKEN" npx --yes vercel --prod --yes >/dev/null ) \
          || warn "Vercel CLI deploy returned non-zero — check the Vercel dashboard"
        ok "Vercel deploy requested"
      else
        warn "npx unavailable — skipping Vercel CLI deploy"
      fi
    else
      warn "VERCEL_TOKEN not set → BLOCKED-ON-OWNER: frontend deploy must be triggered in the Vercel dashboard (or export VERCEL_TOKEN)"
      blocked=1
    fi
  fi

  if [ -n "${RENDER_API_KEY:-}" ] && [ -n "${RENDER_SERVICE_ID:-}" ]; then
    local hdr; hdr="$(mktemp /tmp/${SCRIPT_NAME}-hdr.XXXXXX)"; chmod 600 "$hdr"
    printf 'Authorization: Bearer %s\n' "$RENDER_API_KEY" > "$hdr"
    local code
    code="$(curl -sS -o /tmp/${SCRIPT_NAME}-render.json -w '%{http_code}' \
      -X POST -H @"$hdr" -H 'Content-Type: application/json' \
      -d '{"clearCache":"do_not_clear"}' \
      "https://api.render.com/v1/services/${RENDER_SERVICE_ID}/deploys" || echo 000)"
    rm -f "$hdr"
    case "$code" in
      2*) ok "Render deploy triggered (HTTP $code)" ;;
      *)  warn "Render deploy API returned HTTP $code — check RENDER_SERVICE_ID and the dashboard" ;;
    esac
  else
    warn "RENDER_API_KEY/RENDER_SERVICE_ID not set → BLOCKED-ON-OWNER: trigger the backend deploy in the Render dashboard (or push to the production branch)"
    blocked=1
  fi

  if [ "$blocked" = 1 ]; then
    printf '\n  %sBlocked steps need owner credentials:%s VERCEL_TOKEN, RENDER_API_KEY, RENDER_SERVICE_ID\n' "$c_ylw" "$c_reset"
    printf '  See docs/production/DEPLOYMENT.md §12 (BLOCKED-ON-OWNER summary).\n'
    return 3
  fi
  return 0
}

# ── Health wait + smoke ───────────────────────────────────────────────────────
health_wait() {
  local base="$1" timeout="$2" deadline now code body last="" i=0
  deadline=$(( $(date +%s) + timeout ))
  ok "waiting for liveness: GET $base/health/live"
  while :; do
    if curl -sf -m 5 -o /dev/null "$base/health/live"; then break; fi
    now=$(date +%s)
    if [ "$now" -ge "$deadline" ]; then
      printf '\n'
      bad "liveness timeout after ${timeout}s — $base/health/live did not return 200"
      return 1
    fi
    i=$((i+1)); if [ $((i % 10)) -eq 0 ]; then printf '.'; fi
    sleep 1
  done
  printf '.'
  ok "liveness OK"

  ok "waiting for readiness: GET $base/health/ready (200 + status ok)"
  while :; do
    body="$(curl -sS -m 10 -w '\n%{http_code}' "$base/health/ready" 2>/dev/null || true)"
    code="$(printf '%s' "$body" | tail -n1)"
    last="$(printf '%s' "$body" | sed '$d')"
    if [ "$code" = "200" ]; then
      case "$last" in *'"status":"ok"'*|*'"status": "ok"'*) break ;; esac
    fi
    now=$(date +%s)
    if [ "$now" -ge "$deadline" ]; then
      printf '\n'
      bad "readiness timeout after ${timeout}s (last HTTP $code)"
      printf '\n  last readiness payload:\n%s\n' "$last"
      printf '\n  triage: docs/production/OPERATIONS.md §7 (incident runbook) — components.* names the broken dependency.\n'
      printf '  note: redis down on a rediss:// DSN is a known readiness-probe gap — OPERATIONS.md §8.1\n'
      return 1
    fi
    i=$((i+1)); if [ $((i % 5)) -eq 0 ]; then printf '.'; fi
    sleep 2
  done
  printf '\n'
  ok "readiness OK: $last"
}

rollback_hint() {
  printf '\n%s---- rollback hint ----%s\n' "$c_ylw" "$c_reset"
  printf '  backend : Render → redeploy the previous successful deploy (stateless, instant)\n'
  printf '  frontend: Vercel → promote the previous deployment\n'
  printf '  database: scripts/rollback-prod.sh --dry-run   (then --confirm; snapshot first)\n'
  printf '  decision rules: docs/production/OPERATIONS.md §3.4 and §7.4\n'
}

verify_deployment() {
  step "verify deployment"
  [ -n "$API_URL" ] || die "--verify requires --api-url (or PROD_API_URL in the env)" 2
  API_URL="${API_URL%/}"
  ok "target API: $API_URL (no credentials printed)"
  if ! health_wait "$API_URL" "$TIMEOUT"; then rollback_hint; exit 1; fi

  local legacy metrics
  legacy="$(curl -sS -m 10 "$API_URL/health" 2>/dev/null || true)"
  case "$legacy" in *healthy*) ok "legacy GET /health OK" ;; *) warn "legacy GET /health unexpected: $legacy" ;; esac
  metrics="$(curl -sS -m 10 "$API_URL/health/metrics" 2>/dev/null || true)"
  case "$metrics" in *requests_total*) ok "GET /health/metrics OK (observability surface reachable)" ;; *) warn "GET /health/metrics unexpected: $metrics" ;; esac
  if curl -sf -m 10 -o /dev/null "$API_URL/health/metrics/prometheus"; then
    ok "GET /health/metrics/prometheus OK (scrape target)"
  else
    warn "GET /health/metrics/prometheus not reachable"
  fi

  if [ -n "$FE_URL" ]; then
    FE_URL="${FE_URL%/}"
    if curl -sf -m 15 -o /dev/null "$FE_URL/"; then ok "frontend reachable: $FE_URL/"; else bad "frontend not reachable: $FE_URL/"; fi
    if curl -sf -m 15 -o /dev/null "$FE_URL/login"; then ok "SPA deep link OK: $FE_URL/login (rewrite to index.html configured)";
    else warn "SPA deep link $FE_URL/login did not return 200 — check the rewrite/SPA fallback (DEPLOYMENT.md §4.5 step 2)"; fi
  fi

  printf '\n  remaining manual checks (need credentials or a browser): DEPLOYMENT.md §10 post-deploy checklist\n'
}

# ── Main ──────────────────────────────────────────────────────────────────────
printf '%s%s%s — ForexAI Terminal production deploy driver\n' "$c_bold" "$SCRIPT_NAME" "$c_reset"
if [ "$DO_PREFLIGHT" = 1 ]; then preflight; fi

if [ "$DO_BUILD_FE" = 1 ]; then build_frontend; fi
if [ "$DO_BUILD_BE" = 1 ]; then build_backend; fi
if [ "$DO_MIGRATE" = 1 ]; then run_migrations; fi

if [ "$DO_DEPLOY" = 1 ]; then
  set +e; deploy_providers; dep_rc=$?; set -e
  [ "$dep_rc" -eq 0 ] || { [ "$dep_rc" -eq 3 ] && die "deploy step blocked on owner credentials (exit 3)" 3; rollback_hint; exit 1; }
fi

if [ "$DO_VERIFY" = 1 ]; then
  if ! verify_deployment; then rollback_hint; exit 1; fi
elif [ "$DO_DEPLOY" = 1 ]; then
  step "post-deploy verification"
  if [ -n "$API_URL" ]; then
    if ! health_wait "$API_URL" "$TIMEOUT"; then rollback_hint; exit 1; fi
  else
    warn "--api-url not given — skipped post-deploy health wait (set PROD_API_URL or pass --api-url)"
  fi
fi

if [ "$PROBLEMS" -gt 0 ]; then
  printf '\n%s%s: completed with %d warning-level problem(s) — review above.%s\n' "$c_red" "$SCRIPT_NAME" "$PROBLEMS" "$c_reset" >&2
  exit 1
fi
printf '\n%s%s: done — no failures.%s\n' "$c_grn" "$SCRIPT_NAME" "$c_reset"
