#!/usr/bin/env bash
set -Eeuo pipefail
id="${1:-}"; operation="${2:-}"; task="${3:-}"; APP_ROOT="${APP_ROOT:-/opt/chuma}"
WORK="$APP_ROOT/agent/chuma-workspace.sh"
VERIFY="$APP_ROOT/agent/agent-verify.sh"
case "$operation" in
  STATUS|VERIFY) "$VERIFY" ;;
  RESUME) "$WORK" resume SHUMA_SPACE >/dev/null; "$VERIFY" ;;
  SET_TASK)
    [[ -n "$task" && "$task" != *$'\n'* && "$task" != *$'\r'* ]] || exit 64
    "$WORK" set-task SHUMA_SPACE "$task" >/dev/null
    state=$("$WORK" status SHUMA_SPACE)
    grep -q '^task=' <<<"$state"
    printf 'operation=SET_TASK project=SHUMA_SPACE job=%s result=task_persisted\n' "$id"
    ;;
  STOP)
    "$WORK" stop SHUMA_SPACE >/dev/null
    state=$("$WORK" status SHUMA_SPACE)
    grep -q -E 'task_status=(stopped|idle|queued)' <<<"$state"
    printf 'operation=STOP project=SHUMA_SPACE job=%s result=workspace_stopped\n' "$id"
    ;;
  *) echo "operation_not_allowed" >&2; exit 77 ;;
esac
