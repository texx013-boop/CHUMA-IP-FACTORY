#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
COMPOSE_FILE="${APP_ROOT}/infra/compose.yml"
ENV_FILE="${APP_ROOT}/infra/.env"

usage() {
  echo "Usage: $0 {status|logs|restart|update|backup|health}"
}

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "Run as root." >&2
    exit 1
  fi
}

case "${1:-}" in
  status)
    cd "${APP_ROOT}/infra"
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
    ;;
  logs)
    cd "${APP_ROOT}/infra"
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail="${2:-200}" app
    ;;
  restart)
    require_root
    cd "${APP_ROOT}/infra"
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" restart
    ;;
  update)
    require_root
    cd "${APP_ROOT}/infra"
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build
    ;;
  backup)
    require_root
    cd "${APP_ROOT}/infra"
    ./backup.sh
    ;;
  health)
    curl -fsS http://127.0.0.1:8097/health >/dev/null
    echo "CHUMA health: OK"
    ;;
  *)
    usage
    exit 2
    ;;
esac
