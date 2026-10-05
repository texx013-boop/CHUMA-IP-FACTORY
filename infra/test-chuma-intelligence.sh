#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/agent"
cp infra/chuma-intelligence.sh "$ROOT/agent/chuma-intelligence.sh"; chmod 755 "$ROOT/agent/chuma-intelligence.sh"
export APP_ROOT="$ROOT"; export CHUMA_CONTROL_ROOT="$ROOT/control"
I="$ROOT/agent/chuma-intelligence.sh"
out="$("$I" autonomy status)"; grep -q "^autonomy_mode=L3$" <<<"$out"
out="$("$I" autonomy set L3)"; grep -q "^autonomy.set=ok$" <<<"$out"
if "$I" autonomy set L4 >/dev/null 2>&1; then echo "L4 reservation failed"; exit 1; fi
out="$("$I" goal set FILM_COMBAIN 'working MVP' 'verified final.mp4' medium)"
grep -q '^goal.set=ok$' <<<"$out"
grep -q '^status=active$' <<<"$out"
out="$("$I" decision add FILM_COMBAIN decision001 'keep server authoritative' 'single source of truth' 'independent project copies')"
grep -q '^decision.add=ok$' <<<"$out"
out="$("$I" decision list FILM_COMBAIN)"; grep -q 'decision001' <<<"$out"
"$I" event FILM_COMBAIN test 'failure simulated' >/dev/null
"$I" checkpoint FILM_COMBAIN build 'build verified' >/dev/null
out="$("$I" recovery status FILM_COMBAIN)"; grep -q '^stage=build$' <<<"$out"
out="$("$I" goal update FILM_COMBAIN blocked 'build failed' 'restore checkpoint' )"
grep -q '^status=blocked$' <<<"$out"
out="$("$I" watch FILM_COMBAIN)"; grep -q 'signal=goal_blocked' <<<"$out"
out="$("$I" context FILM_COMBAIN)"; grep -q 'CHUMA CONTEXT' <<<"$out"; grep -q "^autonomy_mode=L3$" <<<"$out"
echo 'CHUMA Intelligence Core: OK'
