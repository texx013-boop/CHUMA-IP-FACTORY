#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
FILE="docs/CHUMA_INTERACTION_CORE_SPEC.md"
test -f "$FILE"
grep -q "MAX AUTONOMOUS + FINISH" "$FILE"
grep -q "Physical Action Gate" "$FILE"
grep -q "Channel router" "$FILE"
grep -q "Self-learning may improve defenses" "$FILE"
grep -q "never request passwords" "$FILE"
grep -q "Cross-device continuity" "$FILE"
echo "CHUMA Interaction Core contract: OK"
