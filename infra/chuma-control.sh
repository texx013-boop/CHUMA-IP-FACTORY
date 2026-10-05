#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
STATE_DIR="$CONTROL_ROOT/state"
PROJECTS_DIR="$CONTROL_ROOT/projects"
INCOMING_DIR="$CONTROL_ROOT/incoming"
RELEASES_DIR="$CONTROL_ROOT/releases"
LOG_FILE="$STATE_DIR/control.log"
REGISTRY_FILE="${CHUMA_PROJECT_REGISTRY:-$PROJECTS_DIR/registry.env}"

mkdir -p "$STATE_DIR" "$PROJECTS_DIR" "$INCOMING_DIR" "$RELEASES_DIR"
chmod 700 "$CONTROL_ROOT" "$STATE_DIR" "$PROJECTS_DIR" "$INCOMING_DIR" "$RELEASES_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }

init_registry() {
  if [[ ! -f "$REGISTRY_FILE" ]]; then
    cat > "$REGISTRY_FILE" <<'EOF'
# CHUMA project registry.
SHUMA_SPACE=enabled
FILM_COMBAIN=enabled
PERSONAL_AI_COMPANION=enabled
EOF
    chmod 600 "$REGISTRY_FILE"
    log "project registry initialized: $REGISTRY_FILE"
  fi
}

status() {
  init_registry
  printf 'CHUMA CONTROL\n'
  printf 'control_root=%s\n' "$CONTROL_ROOT"
  printf 'incoming=%s\n' "$INCOMING_DIR"
  printf 'releases=%s\n' "$RELEASES_DIR"
  printf 'registry=%s\n' "$REGISTRY_FILE"
  printf 'registry_present=%s\n' "$([[ -f "$REGISTRY_FILE" ]] && echo true || echo false)"
  printf 'incoming_files=%s\n' "$(find "$INCOMING_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')"
}

registry() { init_registry; cat "$REGISTRY_FILE"; }

health() {
  local failed=0
  for unit in chuma-agent.service chuma-auto-update.service chuma-watchdog.service chuma-security-agent.service; do
    if ! systemctl is-active --quiet "$unit"; then
      printf 'service.%s=down\\n' "$unit"
      failed=1
    else
      printf 'service.%s=ok\\n' "$unit"
    fi
  done
  if systemctl is-active --quiet chuma-backup.timer; then printf 'backup.timer=ok\\n'; else printf 'backup.timer=down\\n'; failed=1; fi
  if systemctl is-active --quiet chuma-control.timer; then printf 'control.timer=ok\\n'; else printf 'control.timer=down\\n'; failed=1; fi
  if curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then printf 'app.health=ok\\n'; else printf 'app.health=down\\n'; failed=1; fi
  return "$failed"
}

usage() {
  cat <<'EOF'
CHUMA CONTROL
Usage: chuma-control.sh {status|registry|health|init}
EOF
}

case "${1:-status}" in
  status) status ;;
  registry) registry ;;
  init) init_registry ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 64 ;;
esac
