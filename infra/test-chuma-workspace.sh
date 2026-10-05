#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/agent"
cp infra/chuma-workspace.sh "$ROOT/agent/chuma-workspace.sh"
cp infra/chuma-control.sh "$ROOT/agent/chuma-control.sh"
chmod 755 "$ROOT/agent/"*.sh

export APP_ROOT="$ROOT"
export CHUMA_CONTROL_ROOT="$ROOT/control"

out="$("$ROOT/agent/chuma-workspace.sh" resume FILM_COMBAIN)"
grep -q '^workspace.resume=ok$' <<<"$out"
grep -q '^project_id=FILM_COMBAIN$' <<<"$out"
grep -q '^status=ready$' <<<"$out"

session_one='phone:session001'
session_two='windows:session002'
out="$("$ROOT/agent/chuma-workspace.sh" open FILM_COMBAIN "$session_one")"
grep -q '^workspace.open=ok$' <<<"$out"
grep -q '^workspace.lock=ok$' <<<"$out"

if "$ROOT/agent/chuma-workspace.sh" lock FILM_COMBAIN "$session_two" 60 >/dev/null 2>&1; then
  echo 'concurrent lock validation failed'
  exit 1
fi

if "$ROOT/agent/chuma-workspace.sh" release FILM_COMBAIN "$session_two" >/dev/null 2>&1; then
  echo 'owner validation failed'
  exit 1
fi

out="$("$ROOT/agent/chuma-workspace.sh" release FILM_COMBAIN "$session_one")"
grep -q '^workspace.release=ok$' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" lock FILM_COMBAIN "$session_two" 60)"
grep -q '^workspace.lock=ok$' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" history FILM_COMBAIN)"
grep -q 'action=lock result=denied_busy' <<<"$out"
grep -q 'action=release result=denied_owner' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" safe-mode on)"
grep -q '^safe_mode=on$' <<<"$out"
out="$("$ROOT/agent/chuma-workspace.sh" safe-mode status)"
grep -q '^safe_mode=on$' <<<"$out"
out="$("$ROOT/agent/chuma-workspace.sh" status FILM_COMBAIN)"
grep -q '^safe_mode=on$' <<<"$out"

out="$("$ROOT/agent/chuma-workspace.sh" stop FILM_COMBAIN)"
grep -q '^workspace.stop=ok$' <<<"$out"
out="$("$ROOT/agent/chuma-workspace.sh" status FILM_COMBAIN)"
grep -q '^task_status=stopped$' <<<"$out"
grep -q '^workspace_lock=none$' <<<"$out"

if "$ROOT/agent/chuma-workspace.sh" status '../escape' >/dev/null 2>&1; then
  echo 'path validation failed'
  exit 1
fi
if "$ROOT/agent/chuma-workspace.sh" lock FILM_COMBAIN bad 60 >/dev/null 2>&1; then
  echo 'session validation failed'
  exit 1
fi
if "$ROOT/agent/chuma-workspace.sh" lock FILM_COMBAIN "$session_two" 10 >/dev/null 2>&1; then
  echo 'lease validation failed'
  exit 1
fi

out="$("$ROOT/agent/chuma-control.sh" workspace status FILM_COMBAIN)"
grep -q '^project_id=FILM_COMBAIN$' <<<"$out"

echo 'CHUMA Anywhere Workspace: OK'
