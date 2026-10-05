#!/usr/bin/env bash
set -Eeuo pipefail
id="$1"; task="$2"; APP_ROOT="${APP_ROOT:-/opt/chuma}"
# Project executor: bounded, non-shell task dispatch. Extend only with explicit operations.
case "$task" in
  *"status"*|*"проверь"*|*"провер"*) "$APP_ROOT/agent/agent-verify.sh"; exit $?;;
  *"resume"*|*"продолж"*) "$APP_ROOT/agent/chuma-workspace.sh" resume SHUMA_SPACE >/dev/null; "$APP_ROOT/agent/agent-verify.sh"; exit $?;;
  *) echo "executor=SHUMA_SPACE job=$id result=task_requires_project_operation"; exit 0;;
esac
