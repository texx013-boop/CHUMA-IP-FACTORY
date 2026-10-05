#!/usr/bin/env bash
set -Eeuo pipefail
parse(){ local t="$*"; [[ -n "$t" ]] || exit 64; local mode=NORMAL risk=WRITE; [[ "$t" =~ (^|[[:space:]])(SAFE|NORMAL|AUTONOMOUS|MAX_AUTONOMOUS)([[:space:]]|$) ]] && mode="${BASH_REMATCH[2]}"; [[ "$t" =~ (^|[[:space:]])(READ|WRITE|BUILD|TEST|DEPLOY|NETWORK|DATABASE|DOCKER|SERVER)([[:space:]]|$) ]] && risk="${BASH_REMATCH[2]}"; printf 'mode=%s\nrisk=%s\ntask=%s\n' "$mode" "$risk" "$t"; }
case "${1:-}" in parse) shift; parse "$@";; *) echo "usage: parse TASK" >&2; exit 64;; esac
