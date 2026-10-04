#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
COMPOSE_FILE="${APP_ROOT}/infra/compose.yml"
ENV_FILE="${APP_ROOT}/infra/.env"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then
    echo "CHUMA verification: OK"
    exit 0
  fi
  sleep 2
done
echo "CHUMA verification: FAILED" >&2
exit 1
