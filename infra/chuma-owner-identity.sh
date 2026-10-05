#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${CHUMA_CONTROL_ROOT:-/opt/chuma/control}"
STATE="$ROOT/state"
OWNER_FILE="$STATE/owner-identity"
mkdir -p "$STATE"; chmod 700 "$STATE"
init(){
  if [[ ! -f "$OWNER_FILE" ]]; then
    umask 077
    printf 'owner_id=OWNER-%s\ncreated_at=%s\n' "$(openssl rand -hex 12)" "$(date -Is)" > "$OWNER_FILE"
    chmod 600 "$OWNER_FILE"
  fi
  cat "$OWNER_FILE"
}
id(){ init >/dev/null; sed -n 's/^owner_id=//p' "$OWNER_FILE"; }
case "${1:-init}" in init) init;; id) id;; *) echo "usage: init|id" >&2; exit 64;; esac
