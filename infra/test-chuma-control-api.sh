#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m py_compile "$ROOT/infra/chuma-control-api.py"
bash -n "$ROOT/infra/chuma-workspace.sh"
bash -n "$ROOT/infra/chuma-control.sh"
grep -q "PAIRING_TTL=10\*60" "$ROOT/infra/chuma-control-api.py"
grep -q "Secure" "$ROOT/infra/chuma-control-api.py"
grep -q "PAIRING_META_FILE" "$ROOT/infra/chuma-control-api.py"
echo "CHUMA control API syntax: OK"
