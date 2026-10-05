#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${CHUMA_CONTROL_ROOT:-/opt/chuma/control}"
DIR="$ROOT/state/approvals"; mkdir -p "$DIR"; chmod 700 "$DIR"
valid(){ [[ "${1:-}" =~ ^JOB-[0-9]{8}$ ]]; }
request(){ local id="$1" f="$DIR/$id"; valid "$id" || return 64; printf 'status=PENDING\nupdated_at=%s\n' "$(date -Is)" > "$f"; chmod 600 "$f"; }
set_status(){ local id="$1" st="$2" f="$DIR/$id"; valid "$id" || return 64; [[ "$st" =~ ^(PENDING|APPROVED|DENIED)$ ]] || return 64; printf 'status=%s\nupdated_at=%s\n' "$st" "$(date -Is)" > "$f"; chmod 600 "$f"; }
get(){ [[ -f "$DIR/$1" ]] && cat "$DIR/$1" || printf 'status=NONE\n'; }
case "${1:-}" in request) request "$2";; approve|deny) set_status "$2" "${1^^}D";; get) get "$2";; *) echo "usage: request|approve|deny|get JOB-ID" >&2; exit 64;; esac
