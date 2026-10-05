#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${CHUMA_CONTROL_ROOT:-/opt/chuma/control}"
POLICY="$ROOT/state/capabilities.env"; mkdir -p "$(dirname "$POLICY")"; chmod 700 "$(dirname "$POLICY")"
init(){ [[ -f "$POLICY" ]] || { cat >"$POLICY"<<'EOF'
READ=allow
WRITE=allow
BUILD=allow
TEST=allow
DEPLOY=deny
NETWORK=deny
DATABASE=deny
DOCKER=deny
SERVER=deny
EOF
chmod 600 "$POLICY"; }; }
allowed(){ init; local c="$1" v; v=$(grep -E "^$c=" "$POLICY" | cut -d= -f2- || true); [[ "$v" == allow ]]; }
mode_ceiling(){ case "$1" in SAFE) echo READ;; NORMAL) echo BUILD;; AUTONOMOUS) echo TEST;; MAX_AUTONOMOUS) echo DEPLOY;; *) return 64;; esac; }
check(){ local mode="$1" cap="$2"; case "$mode:$cap" in SAFE:READ|NORMAL:READ|NORMAL:WRITE|NORMAL:BUILD|NORMAL:TEST|AUTONOMOUS:READ|AUTONOMOUS:WRITE|AUTONOMOUS:BUILD|AUTONOMOUS:TEST|AUTONOMOUS:NETWORK|MAX_AUTONOMOUS:*) allowed "$cap";; *) return 77;; esac; }
case "${1:-}" in init) init;; check) check "$2" "$3";; allowed) allowed "$2";; *) echo "usage: init|check MODE CAPABILITY|allowed CAPABILITY" >&2; exit 64;; esac
