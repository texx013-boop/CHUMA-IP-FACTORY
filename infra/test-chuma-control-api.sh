#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m py_compile "$ROOT/infra/chuma-control-api.py"
bash -n "$ROOT/infra/chuma-workspace.sh"
bash -n "$ROOT/infra/chuma-control.sh"
echo "CHUMA control API syntax: OK"
