#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
INFRA_DIR="${APP_ROOT}/infra"
STATE_DIR="${APP_ROOT}/agent"
MODE="${CHUMA_AGENT_MODE:-safe}"
AUTO_UPDATE="${CHUMA_AGENT_AUTO_UPDATE:-false}"
REPO_URL="${CHUMA_AGENT_REPO_URL:-https://github.com/texx013-boop/CHUMA-IP-FACTORY.git}"

log(){ printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$STATE_DIR/agent.log"; }
healthy(){ curl -fsS --max-time 5 http://127.0.0.1:8097/health >/dev/null 2>&1; }

[[ "$MODE" == "auto" && "$AUTO_UPDATE" == "true" ]] || exit 0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log "checking for update"
if ! git clone --depth 1 "$REPO_URL" "$TMP/repo" >/dev/null 2>&1; then
  log "update check failed"
  exit 0
fi

if ! git -C "$TMP/repo" rev-parse HEAD > "$STATE_DIR/available_revision"; then
  exit 0
fi

CURRENT="$(cat "$STATE_DIR/current_revision" 2>/dev/null || true)"
AVAILABLE="$(cat "$STATE_DIR/available_revision")"
[[ -n "$AVAILABLE" && "$AVAILABLE" != "$CURRENT" ]] || exit 0

"$INFRA_DIR/agent-backup.sh" >/dev/null
rm -rf "$APP_ROOT/release-next"
mkdir -p "$APP_ROOT/release-next"
tar -C "$TMP/repo" -cf - . | tar -C "$APP_ROOT/release-next" -xf -
cp "$INFRA_DIR/.env" "$APP_ROOT/release-next/infra/.env"

cd "$APP_ROOT/release-next/infra"
if ! docker compose --env-file .env -f compose.yml config -q; then
  log "update rejected: compose validation failed"
  exit 1
fi
if ! docker compose --env-file .env -f compose.yml up -d --build; then
  log "update failed during build/start"
  exit 1
fi

for i in $(seq 1 30); do
  if healthy; then
    cp "$AVAILABLE" "$STATE_DIR/current_revision"
    log "update applied: $AVAILABLE"
    exit 0
  fi
  sleep 2
done

log "update failed health verification; rollback required"
exit 1
