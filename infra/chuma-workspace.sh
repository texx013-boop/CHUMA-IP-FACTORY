#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
STATE_ROOT="$CONTROL_ROOT/state/workspaces"
LOCK_ROOT="$CONTROL_ROOT/state/workspace-locks"
HISTORY_ROOT="$CONTROL_ROOT/state/workspace-history"
SAFE_MODE_FILE="$CONTROL_ROOT/state/SAFE_MODE"
DEFAULT_LEASE_SECONDS="${CHUMA_WORKSPACE_LEASE_SECONDS:-900}"

mkdir -p "$STATE_ROOT" "$LOCK_ROOT" "$HISTORY_ROOT"
chmod 700 "$STATE_ROOT" "$LOCK_ROOT" "$HISTORY_ROOT"

usage() {
  cat <<'EOF'
CHUMA ANYWHERE WORKSPACE
Usage:
  chuma-workspace.sh status <project>
  chuma-workspace.sh resume <project>
  chuma-workspace.sh open <project> <session>
  chuma-workspace.sh lock <project> <session> [lease_seconds]
  chuma-workspace.sh release <project> <session>
  chuma-workspace.sh stop <project>
  chuma-workspace.sh history <project>
  chuma-workspace.sh safe-mode <on|off|status>
EOF
}

valid_project() { [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]]; }
valid_session() { [[ "$1" =~ ^[A-Za-z0-9._:-]{8,128}$ ]]; }

state_file() {
  local project="$1"
  valid_project "$project" || { echo "invalid project id" >&2; exit 64; }
  printf '%s/%s.state' "$STATE_ROOT" "$project"
}

lock_dir() {
  local project="$1"
  valid_project "$project" || { echo "invalid project id" >&2; exit 64; }
  printf '%s/%s.lock' "$LOCK_ROOT" "$project"
}

history_file() {
  local project="$1"
  valid_project "$project" || { echo "invalid project id" >&2; exit 64; }
  printf '%s/%s.log' "$HISTORY_ROOT" "$project"
}

ensure_state() {
  local project="$1" file
  file="$(state_file "$project")"
  if [[ ! -f "$file" ]]; then
    umask 077
    cat > "$file" <<EOF
project_id=$project
status=ready
current_task=
task_status=idle
last_successful_stage=
next_action=
workspace_lock=none
workspace_session=
workspace_lease_expires=
last_verified_result=
updated_at=$(date -Is)
EOF
    chmod 600 "$file"
  fi
}

record() {
  local project="$1" action="$2" result="$3" session="${4:-}"
  printf '%s action=%s result=%s session=%s
' "$(date -Is)" "$action" "$result" "$session" >> "$(history_file "$project")"
  chmod 600 "$(history_file "$project")"
}

read_lock_value() {
  local project="$1" key="$2" dir
  dir="$(lock_dir "$project")"
  [[ -f "$dir/$key" ]] && cat "$dir/$key" || true
}

clear_lock_state() {
  local project="$1" file
  file="$(state_file "$project")"
  sed -i 's/^workspace_lock=.*/workspace_lock=none/; s/^workspace_session=.*/workspace_session=/; s/^workspace_lease_expires=.*/workspace_lease_expires=/' "$file"
}

expire_lock_if_needed() {
  local project="$1" dir expires now
  dir="$(lock_dir "$project")"
  [[ -d "$dir" ]] || return 0
  expires="$(read_lock_value "$project" expires)"
  now="$(date +%s)"
  if [[ "$expires" =~ ^[0-9]+$ ]] && (( expires <= now )); then
    rm -rf -- "$dir"
    clear_lock_state "$project"
    record "$project" lease_expired "ok"
  fi
}

status() {
  local project="$1" file
  ensure_state "$project"
  expire_lock_if_needed "$project"
  file="$(state_file "$project")"
  cat "$file"
  if [[ -f "$SAFE_MODE_FILE" ]]; then printf 'safe_mode=on
'; else printf 'safe_mode=off
'; fi
}

resume() {
  local project="$1"
  ensure_state "$project"
  expire_lock_if_needed "$project"
  record "$project" resume "ok"
  printf 'workspace.resume=ok
'
  cat "$(state_file "$project")"
}

lock() {
  local project="$1" session="$2" lease="${3:-$DEFAULT_LEASE_SECONDS}" dir now expires
  valid_project "$project" || { echo "invalid project id" >&2; return 64; }
  valid_session "$session" || { echo "invalid session id" >&2; return 64; }
  if [[ -f "$SAFE_MODE_FILE" ]]; then
    echo "workspace.lock=blocked_safe_mode" >&2
    record "$project" lock "denied_safe_mode" "$session"
    return 78
  fi
  [[ "$lease" =~ ^[0-9]+$ ]] && (( lease >= 30 && lease <= 86400 )) || { echo "invalid lease seconds" >&2; return 64; }
  ensure_state "$project"
  expire_lock_if_needed "$project"
  dir="$(lock_dir "$project")"
  if ! mkdir "$dir" 2>/dev/null; then
    echo "workspace.lock=busy" >&2
    record "$project" lock "denied_busy" "$session"
    return 75
  fi
  chmod 700 "$dir"
  now="$(date +%s)"; expires=$((now + lease))
  printf '%s
' "$session" > "$dir/session"
  printf '%s
' "$expires" > "$dir/expires"
  printf '%s
' "$(date -Is)" > "$dir/acquired_at"
  chmod 600 "$dir"/*
  sed -i "s/^workspace_lock=.*/workspace_lock=held/; s/^workspace_session=.*/workspace_session=$session/; s/^workspace_lease_expires=.*/workspace_lease_expires=$expires/; s/^updated_at=.*/updated_at=$(date -Is)/" "$(state_file "$project")"
  record "$project" lock "ok" "$session"
  printf 'workspace.lock=ok
project=%s
session=%s
lease_expires=%s
' "$project" "$session" "$expires"
}

release() {
  local project="$1" session="$2" dir owner
  valid_session "$session" || { echo "invalid session id" >&2; return 64; }
  ensure_state "$project"; expire_lock_if_needed "$project"
  dir="$(lock_dir "$project")"
  if [[ ! -d "$dir" ]]; then
    clear_lock_state "$project"; record "$project" release "noop" "$session"
    printf 'workspace.release=ok
'; return 0
  fi
  owner="$(read_lock_value "$project" session)"
  [[ "$owner" == "$session" ]] || { echo "workspace.lock=owner_mismatch" >&2; record "$project" release "denied_owner" "$session"; return 77; }
  rm -rf -- "$dir"
  clear_lock_state "$project"
  record "$project" release "ok" "$session"
  printf 'workspace.release=ok
'
}

open_workspace() {
  local project="$1" session="$2"
  resume "$project" >/dev/null
  lock "$project" "$session"
  printf 'workspace.open=ok
'
}

stop() {
  local project="$1" file
  ensure_state "$project"
  file="$(state_file "$project")"
  expire_lock_if_needed "$project"
  if [[ -d "$(lock_dir "$project")" ]]; then rm -rf -- "$(lock_dir "$project")"; fi
  sed -i 's/^workspace_lock=.*/workspace_lock=none/; s/^workspace_session=.*/workspace_session=/; s/^workspace_lease_expires=.*/workspace_lease_expires=/; s/^task_status=.*/task_status=stopped/; s/^updated_at=.*/updated_at='"$(date -Is)"'/' "$file"
  record "$project" stop "ok"
  printf 'workspace.stop=ok
'
}

history() {
  local project="$1" file
  ensure_state "$project"
  file="$(history_file "$project")"
  if [[ -f "$file" ]]; then cat "$file"; else printf 'history=empty
'; fi
}

safe_mode() {
  case "$1" in
    on) umask 077; printf '%s\n' "$(date -Is)" > "$SAFE_MODE_FILE"; chmod 600 "$SAFE_MODE_FILE"; printf 'safe_mode=on\n' ;;
    off) rm -f -- "$SAFE_MODE_FILE"; printf 'safe_mode=off\n' ;;
    status) [[ -f "$SAFE_MODE_FILE" ]] && printf 'safe_mode=on\n' || printf 'safe_mode=off\n' ;;
    *) echo "Usage: safe-mode <on|off|status>" >&2; return 64 ;;
  esac
}

case "${1:-}" in
  status|resume|history)
    [[ $# -eq 2 ]] || { usage >&2; exit 64; }; "$1" "$2" ;;
  open)
    [[ $# -eq 3 ]] || { usage >&2; exit 64; }; open_workspace "$2" "$3" ;;
  lock)
    [[ $# -ge 3 && $# -le 4 ]] || { usage >&2; exit 64; }; lock "$2" "$3" "${4:-$DEFAULT_LEASE_SECONDS}" ;;
  release)
    [[ $# -eq 3 ]] || { usage >&2; exit 64; }; release "$2" "$3" ;;
  stop)
    [[ $# -eq 2 ]] || { usage >&2; exit 64; }; stop "$2" ;;
  safe-mode)
    [[ $# -eq 2 ]] || { usage >&2; exit 64; }; safe_mode "$2" ;;
  *) usage >&2; exit 64 ;;
esac
