#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
SNAP_DIR="${STATE_DIR}/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${SNAP_DIR}/${STAMP}"
COMPOSE_FILE="${APP_ROOT}/infra/compose.yml"
ENV_FILE="${APP_ROOT}/infra/.env"

mkdir -p "$DEST"
chmod 700 "$DEST"
cp "$COMPOSE_FILE" "$DEST/compose.snapshot"
if [[ -f "$ENV_FILE" ]]; then cp "$ENV_FILE" "$DEST/env.snapshot"; fi
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config > "$DEST/compose.rendered"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps > "$DEST/services.txt" || true
printf '%s\n' "$DEST"
