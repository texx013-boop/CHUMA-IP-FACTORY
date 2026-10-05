#!/usr/bin/env bash
set -Eeuo pipefail
id="$1"; task="$2"; APP_ROOT="${APP_ROOT:-/opt/chuma}"
case "$task" in
  *"status"*|*"проверь"*|*"провер"*) "$APP_ROOT/agent/agent-verify.sh"; exit $?;;
  *"resume"*|*"продолж"*) "$APP_ROOT/agent/chuma-workspace.sh" resume PERSONAL_AI_COMPANION >/dev/null; "$APP_ROOT/agent/agent-verify.sh"; exit $?;;
  *) echo "executor=PERSONAL_AI_COMPANION job=$id result=task_requires_project_operation"; exit 0;;
esac
