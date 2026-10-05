#!/usr/bin/env bash
set -Eeuo pipefail
id="${1:-}"; operation="${2:-}"; task="${3:-}"; APP_ROOT="${APP_ROOT:-/opt/chuma}"
WORK="$APP_ROOT/agent/chuma-workspace.sh"
VERIFY="$APP_ROOT/agent/agent-verify.sh"
case "$operation" in
  STATUS|VERIFY) "$VERIFY" ;;
  RESUME) "$WORK" resume PERSONAL_AI_COMPANION >/dev/null; "$VERIFY" ;;
  SET_TASK)
    [[ -n "$task" && "$task" != *$'\n'* && "$task" != *$'\r'* ]] || exit 64
    "$WORK" set-task PERSONAL_AI_COMPANION "$task" >/dev/null
    state=$("$WORK" status PERSONAL_AI_COMPANION)
    grep -q '^task=' <<<"$state"
    printf 'operation=SET_TASK project=PERSONAL_AI_COMPANION job=%s result=task_persisted\n' "$id"
    ;;
  STOP)
    "$WORK" stop PERSONAL_AI_COMPANION >/dev/null
    state=$("$WORK" status PERSONAL_AI_COMPANION)
    grep -q -E 'task_status=(stopped|idle|queued)' <<<"$state"
    printf 'operation=STOP project=PERSONAL_AI_COMPANION job=%s result=workspace_stopped\n' "$id"
    ;;
  *) echo "operation_not_allowed" >&2; exit 77 ;;
esac
