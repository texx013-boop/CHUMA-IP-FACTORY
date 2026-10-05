#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
STATE_DIR="$CONTROL_ROOT/state"
PROJECTS_DIR="$CONTROL_ROOT/projects"
INCOMING_DIR="$CONTROL_ROOT/incoming"
RELEASES_DIR="$CONTROL_ROOT/releases"
WORKSPACE_STATE_DIR="$STATE_DIR/workspaces"
WORKSPACE_LOCK_DIR="$STATE_DIR/workspace-locks"
LOG_FILE="$STATE_DIR/control.log"
REGISTRY_FILE="${CHUMA_PROJECT_REGISTRY:-$PROJECTS_DIR/registry.env}"

mkdir -p "$STATE_DIR" "$PROJECTS_DIR" "$INCOMING_DIR" "$RELEASES_DIR" "$WORKSPACE_STATE_DIR" "$WORKSPACE_LOCK_DIR"
chmod 700 "$CONTROL_ROOT" "$STATE_DIR" "$PROJECTS_DIR" "$INCOMING_DIR" "$RELEASES_DIR" "$WORKSPACE_STATE_DIR" "$WORKSPACE_LOCK_DIR"
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
  printf 'workspace_state=%s\n' "$WORKSPACE_STATE_DIR"
  printf 'workspace_locks=%s\n' "$WORKSPACE_LOCK_DIR"
  printf 'registry_present=%s\n' "$([[ -f "$REGISTRY_FILE" ]] && echo true || echo false)"
  printf 'incoming_files=%s\n' "$(find "$INCOMING_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')"
}

registry() { init_registry; cat "$REGISTRY_FILE"; }

intelligence() {
  [[ $# -ge 2 ]] || { printf 'Usage: chuma-control.sh intelligence <command> <project> ...\n' >&2; return 64; }
  "$APP_ROOT/agent/chuma-intelligence.sh" "$@"
}

intelligence() {
  [[ $# -ge 2 ]] || { printf 'Usage: chuma-control.sh intelligence <command> <project> ...\n' >&2; return 64; }
  "$APP_ROOT/agent/chuma-intelligence.sh" "$@"
}

workspace() {
  [[ $# -ge 2 ]] || { printf 'Usage: chuma-control.sh workspace {status|resume|stop} <project>\n' >&2; return 64; }
  "$APP_ROOT/agent/chuma-workspace.sh" "$@"
}

release() {
  [[ $# -eq 2 ]] || { printf "Usage: chuma-control.sh release {verify|stage|promote} <bundle>\n" >&2; return 64; }
  "$APP_ROOT/agent/chuma-release.sh" "$1" "$2"
}

health() {
  local failed=0
  init_registry
  for project in SHUMA_SPACE FILM_COMBAIN PERSONAL_AI_COMPANION; do
    if ! grep -q "^${project}=enabled$" "$REGISTRY_FILE"; then
      printf 'project.%s=disabled\\n' "$project"
      failed=1
    else
      printf 'project.%s=enabled\\n' "$project"
    fi
  done
  for unit in chuma-agent.service chuma-auto-update.service chuma-watchdog.service chuma-security-agent.service; do
    if ! systemctl is-active --quiet "$unit"; then
      printf 'service.%s=down\n' "$unit"
      failed=1
    else
      printf 'service.%s=ok\n' "$unit"
    fi
  done
  if systemctl is-active --quiet chuma-backup.timer; then printf 'backup.timer=ok\n'; else printf 'backup.timer=down\n'; failed=1; fi
  if systemctl is-active --quiet chuma-control.timer; then printf 'control.timer=ok\n'; else printf 'control.timer=down\n'; failed=1; fi
  if curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then printf 'app.health=ok\n'; else printf 'app.health=down\n'; failed=1; fi
  return "$failed"
}

reconcile() {
  init_registry
  local rc=0
  health || rc=$?
  printf 'control.reconcile=%s\n' "$([[ "$rc" -eq 0 ]] && echo ok || echo degraded)"
  return "$rc"
}

usage() {
  cat <<'EOF'
CHUMA CONTROL
Usage: chuma-control.sh {status|registry|health|reconcile|init|release|workspace|intelligence} ...
EOF
}

case "${1:-status}" in
  status) status ;;
  registry) registry ;;
  init) init_registry ;;
  health) health ;;
  reconcile) reconcile ;;
  release) release "$2" "$3" ;;
  workspace) shift; workspace "$@" ;;
  intelligence) shift; intelligence "$@" ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 64 ;;
esac
