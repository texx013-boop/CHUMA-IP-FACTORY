#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
STATE_ROOT="$CONTROL_ROOT/state/workspaces"
LOCK_ROOT="$CONTROL_ROOT/state/workspace-locks"
mkdir -p "$STATE_ROOT" "$LOCK_ROOT"
chmod 700 "$STATE_ROOT" "$LOCK_ROOT"

usage() {
  cat <<'EOF'
CHUMA ANYWHERE WORKSPACE
Usage:
  chuma-workspace.sh status <project>
  chuma-workspace.sh resume <project>
  chuma-workspace.sh stop <project>
EOF
}

state_file() {
  local project="$1"
  [[ "$project" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid project id" >&2; exit 64; }
  printf '%s/%s.state' "$STATE_ROOT" "$project"
}

status() {
  local project="$1" file
  file="$(state_file "$project")"
  if [[ ! -f "$file" ]]; then
    printf 'project=%s\nstatus=uninitialized\n' "$project"
    return 0
  fi
  cat "$file"
}

resume() {
  local project="$1" file
  file="$(state_file "$project")"
  if [[ ! -f "$file" ]]; then
    cat > "$file" <<EOF
project_id=$project
status=ready
current_task=
task_status=idle
last_successful_stage=
next_action=
workspace_lock=none
last_verified_result=
EOF
    chmod 600 "$file"
  fi
  printf 'workspace.resume=ok\n'
  cat "$file"
}

stop() {
  local project="$1" file
  file="$(state_file "$project")"
  if [[ -f "$file" ]]; then
    sed -i 's/^workspace_lock=.*/workspace_lock=none/; s/^task_status=.*/task_status=stopped/' "$file"
  fi
  printf 'workspace.stop=ok\n'
}

case "${1:-}" in
  status|resume|stop)
    [[ $# -eq 2 ]] || { usage >&2; exit 64; }
    "$1" "$2"
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac
