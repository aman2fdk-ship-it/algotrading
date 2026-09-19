#!/usr/bin/env bash
# =============================================================================
# ForexAI Terminal — production rollback helper (dry-run by default)
#
# Prints (or, with --confirm, performs) the rollback of a production change:
#   1. the provider rollbacks you should do FIRST (Render redeploy / Vercel promote)
#   2. the Alembic migration state, and the exact downgrade command
#   3. with --confirm: a pre-flight snapshot (--backup-first), the downgrade,
#      a post-downgrade revision check and a readiness check
#
# DATA-LOSS WARNING: this repository currently has a single migration
# (2b91be147303, "initial schema"), so `downgrade -1` from head drops every
# application table. See docs/production/OPERATIONS.md §3 before using
# --confirm. Without --confirm this script changes nothing.
#
# Never prompts for or prints a credential: everything is read from the
# environment (DATABASE_URL, and DATABASE_URL_SYNC for snapshots).
#
# Usage:
#   scripts/rollback-prod.sh                          # dry run: state + plan
#   scripts/rollback-prod.sh --backup-first --confirm # snapshot, then downgrade
#   scripts/rollback-prod.sh --revision <revision> --confirm
#
# Exit codes: 0 = ok / dry-run complete, 1 = failure, 2 = usage error.
# =============================================================================
set -euo pipefail

SCRIPT_NAME="rollback-prod"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REVISION="-1"
CONFIRM=0
BACKUP_FIRST=0
ASSUME_YES=0
API_URL="${PROD_API_URL:-}"
BACKUP_DIR="${BACKUP_DIR:-/tmp}"

c_reset=$'\033[0m'; c_red=$'\033[1;31m'; c_grn=$'\033[1;32m'; c_ylw=$'\033[1;33m'; c_cyn=$'\033[1;36m'
step() { printf '\n%s==> %s%s\n' "$c_cyn" "$*" "$c_reset"; }
ok()   { printf '  %sOK%s   %s\n' "$c_grn" "$c_reset" "$*"; }
warn() { printf '  %sWARN%s %s\n' "$c_ylw" "$c_reset" "$*"; }
die()  { printf '\n%s%s: %s%s\n' "$c_red" "$SCRIPT_NAME" "$*" "$c_reset" >&2; exit "${2:-1}"; }
mask() { printf '%s' "$1" | sed -E 's#(://)[^@/]*@#\1***@#g'; }

usage() { sed -n '3,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --confirm)      CONFIRM=1 ;;
    --backup-first) BACKUP_FIRST=1 ;;
    --dry-run)      CONFIRM=0 ;;
    --revision)     REVISION="${2:-}"; shift ;;
    --api-url)      API_URL="${2:-}"; shift ;;
    --yes|-y)       ASSUME_YES=1 ;;
    -h|--help)      usage 0 ;;
    *) usage 2 ;;
  esac
  shift
done

step "$SCRIPT_NAME — production rollback preparation"
printf '  mode: %s\n' "$([ "$CONFIRM" = 1 ] && echo 'CONFIRM (will change the database)' || echo 'dry run (no changes)')"
[ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL is required (export it from the Secrets store)" 2
ok "target database: $(mask "$DATABASE_URL")"

# ── 1. Provider rollbacks first ───────────────────────────────────────────────
step "1. application rollback (do this first)"
printf '  backend : Render dashboard → the service → Deploys → "Redeploy" the previous successful deploy\n'
printf '  frontend: Vercel dashboard → Deployments → the previous deployment → "Promote to Production"\n'
printf '  When to prefer app rollback over a DB downgrade: OPERATIONS.md §3.4 and §7.4\n'
[ "$REVISION" = "-1" ] && warn "app rollback alone is usually enough — downgrade the database only when the new code wrote an incompatible schema change"

# ── 2. Current migration state ────────────────────────────────────────────────
step "2. current migration state"
cd "$REPO_ROOT/backend"
ok "running: $PYTHON_BIN -m alembic current"
CURRENT="$("$PYTHON_BIN" -m alembic current 2>&1 || true)"
printf '%s\n' "$CURRENT" | sed 's/^/    /'
if printf '%s' "$CURRENT" | grep -qiE 'no such|error|Traceback'; then
  die "could not read the current revision — resolve connectivity/config before rolling back" 1
fi
printf '  heads:\n'; "$PYTHON_BIN" -m alembic heads 2>&1 | sed 's/^/    /' || true
printf '  recent history:\n'; "$PYTHON_BIN" -m alembic history -r -5: 2>&1 | sed 's/^/    /' || true
warn "this repo has ONE migration (initial schema) — a downgrade from head DROPS all application tables"

# ── 3. Optional snapshot ──────────────────────────────────────────────────────
if [ "$BACKUP_FIRST" = 1 ] || [ "$CONFIRM" = 1 ]; then
  step "3. pre-rollback snapshot"
  if command -v pg_dump >/dev/null 2>&1 && [ -n "${DATABASE_URL_SYNC:-}" ]; then
    snap="$BACKUP_DIR/forexai-prerollback-$(date -u +%Y%m%dT%H%M%SZ).dump"
    pg_dump "$DATABASE_URL_SYNC" --format=custom --no-owner --no-privileges --file="$snap"
    size=$(wc -c < "$snap" | tr -d ' ')
    [ "$size" -gt 0 ] || die "snapshot is empty ($snap) — refusing to continue" 1
    pg_restore --list "$snap" >/dev/null || die "snapshot is not readable by pg_restore — refusing to continue" 1
    ok "snapshot verified: $snap ($size bytes) — restore procedure: OPERATIONS.md §4.3"
  else
    [ -n "${DATABASE_URL_SYNC:-}" ] || warn "DATABASE_URL_SYNC not set → no snapshot taken"
    command -v pg_dump >/dev/null 2>&1 || warn "pg_dump not installed → no snapshot taken"
    if [ "$CONFIRM" = 1 ]; then die "refusing to downgrade without a verified snapshot (set DATABASE_URL_SYNC or pass --dry-run)" 1; fi
  fi
else
  step "3. pre-rollback snapshot"; warn "skipped (dry run without --backup-first)"
fi

# ── 4. Downgrade ──────────────────────────────────────────────────────────────
step "4. migration downgrade"
printf '  command: cd backend && %s -m alembic downgrade %s\n' "$PYTHON_BIN" "$REVISION"
if [ "$CONFIRM" != 1 ]; then
  warn "dry run — nothing executed. Re-run with --confirm --backup-first to apply."
  printf '\n  after a confirmed downgrade: verify with `alembic current`, then check GET /health/ready\n'
  exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
  printf '  This will modify the database above (revision target: %s). Type "downgrade" to continue: ' "$REVISION"
  read -r reply
  [ "$reply" = "downgrade" ] || die "aborted by operator" 1
fi

"$PYTHON_BIN" -m alembic downgrade "$REVISION"
ok "downgrade executed"

# ── 5. Verify ─────────────────────────────────────────────────────────────────
step "5. verify"
"$PYTHON_BIN" -m alembic current 2>&1 | sed 's/^/    /'
if [ -n "$API_URL" ]; then
  if curl -sf -m 10 -o /dev/null "${API_URL%/}/health/ready"; then
    ok "readiness OK after rollback: ${API_URL%/}/health/ready"
  else
    warn "readiness not 200 yet — restart the backend revision that matches this schema, then re-check (/health/ready names the broken component)"
  fi
else
  warn "no --api-url given — verify readiness manually"
fi
printf '\n  next: restart the matching backend revision, then run scripts/deploy-prod.sh --verify --api-url <url>\n'
printf '  record the incident and the rollback in the post-incident review (OPERATIONS.md §7.6)\n'
