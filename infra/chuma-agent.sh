#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
INFRA_DIR="${APP_ROOT}/infra"
COMPOSE_FILE="${INFRA_DIR}/compose.yml"
ENV_FILE="${INFRA_DIR}/.env"
STATE_DIR="${APP_ROOT}/agent"
BACKUP_DIR="${STATE_DIR}/backups"
LOG_FILE="${STATE_DIR}/agent.log"
LOCK_FILE="${STATE_DIR}/agent.lock"
CHECK_INTERVAL="${CHUMA_AGENT_INTERVAL:-30}"
MODE="${CHUMA_AGENT_MODE:-safe}"
mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR"
log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
compose() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }
healthy() { curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; }
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
log "agent started mode=$MODE"
while true; do
  if ! docker info >/dev/null 2>&1; then
    log "docker unavailable"
    sleep "$CHECK_INTERVAL"
    continue
  fi
  if ! healthy; then
    log "web health check failed; attempting safe recovery"
    compose restart app || true
    sleep 10
    if ! healthy; then
      log "app recovery failed; restarting stack"
      compose up -d || true
      sleep 15
    fi
  fi
  if healthy; then date +%s > "$STATE_DIR/last_healthy"; fi
  sleep "$CHECK_INTERVAL"
done
