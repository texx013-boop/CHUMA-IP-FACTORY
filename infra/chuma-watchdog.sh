#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
LOG_FILE="${STATE_DIR}/watchdog.log"
INTERVAL="${CHUMA_WATCHDOG_INTERVAL:-60}"

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }

service_active() {
  systemctl is-active --quiet "$1"
}

while true; do
  for svc in chuma-agent.service chuma-auto-update.service chuma-security-agent.service; do
    if ! service_active "$svc"; then
      log "service unhealthy: $svc; attempting restart"
      systemctl restart "$svc" || log "restart failed: $svc"
    fi
  done

  if ! systemctl is-active --quiet chuma-backup.timer; then
    log "backup timer unhealthy; attempting restart"
    systemctl restart chuma-backup.timer || log "backup timer restart failed"
  fi

  if ! curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then
    log "application health check failed"
  else
    date +%s > "$STATE_DIR/watchdog_last_healthy"
    chmod 600 "$STATE_DIR/watchdog_last_healthy"
  fi

  sleep "$INTERVAL"
done
