#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
RELEASE_DIR="${APP_ROOT}/release"
ENV_FILE="${APP_ROOT}/infra/.env"
LOG_FILE="${STATE_DIR}/security.log"
INTERVAL="${CHUMA_SECURITY_INTERVAL:-300}"

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }

audit_once() {
  local failures=0

  if [[ -f "$ENV_FILE" ]]; then
    perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)"
    if [[ "$perms" != "600" ]]; then
      log "security: infra/.env permissions are $perms; expected 600"
      chmod 600 "$ENV_FILE" || failures=$((failures+1))
    fi
  fi

  for path in "$STATE_DIR" "$APP_ROOT"; do
    if [[ -d "$path" ]]; then
      :
    fi
  done

  if [[ -d "$RELEASE_DIR/.git" ]]; then
    log "security: release contains .git metadata; removing"
    rm -rf "$RELEASE_DIR/.git" || failures=$((failures+1))
  fi

  if [[ -d "$RELEASE_DIR" ]]; then
    if grep -RInE --exclude-dir=.git --exclude='*.pyc' --exclude='*.log' --exclude='infra/.env' \
      'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}' \
      "$RELEASE_DIR" >/dev/null 2>&1; then
      log "security: possible credential material detected in release"
      failures=$((failures+1))
    fi
  fi

  if ! systemctl is-enabled --quiet chuma-agent.service; then
    log "security: chuma-agent.service is not enabled"
    failures=$((failures+1))
  fi
  if ! systemctl is-enabled --quiet chuma-auto-update.service; then
    log "security: chuma-auto-update.service is not enabled"
    failures=$((failures+1))
  fi

  date +%s > "$STATE_DIR/security_last_audit"
  chmod 600 "$STATE_DIR/security_last_audit"
  if [[ "$failures" -eq 0 ]]; then
    log "security audit: OK"
  else
    log "security audit: completed with $failures finding(s)"
  fi
}

log "security agent started interval=${INTERVAL}s"
while true; do
  audit_once
  sleep "$INTERVAL"
done
