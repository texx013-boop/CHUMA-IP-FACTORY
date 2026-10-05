#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/agent"
cp infra/chuma-workspace.sh "$ROOT/agent/chuma-workspace.sh"
chmod 755 "$ROOT/agent/chuma-workspace.sh"

export APP_ROOT="$ROOT"
export CHUMA_CONTROL_ROOT="$ROOT/control"

out="$("$ROOT/agent/chuma-workspace.sh" resume FILM_COMBAIN)"
grep -q '^workspace.resume=ok$' <<<"$out"
grep -q '^project_id=FILM_COMBAIN$' <<<"$out"
grep -q '^status=ready$' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" status FILM_COMBAIN)"
grep -q '^task_status=idle$' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" stop FILM_COMBAIN)"
grep -q '^workspace.stop=ok$' <<<"$out"
out="$("$ROOT/agent/chuma-workspace.sh" status FILM_COMBAIN)"
grep -q '^task_status=stopped$' <<<"$out"
grep -q '^workspace_lock=none$' <<<"$out"

if "$ROOT/agent/chuma-workspace.sh" status '../escape' >/dev/null 2>&1; then
  echo 'path validation failed'
  exit 1
fi

echo 'CHUMA Anywhere Workspace: OK'
