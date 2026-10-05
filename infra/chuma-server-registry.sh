#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${CHUMA_CONTROL_ROOT:-/opt/chuma/control}"; F="$ROOT/state/servers.env"; mkdir -p "$(dirname "$F")"; chmod 700 "$(dirname "$F")"
init(){ [[ -f "$F" ]] || { cat >"$F"<<'EOF'
primary|selectel-vds|active|CHUMA_PRIMARY
EOF
chmod 600 "$F"; }; }
list(){ init; cat "$F"; }
case "${1:-}" in init|list) "$1";; *) echo "usage: init|list" >&2; exit 64;; esac
