#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
SNAP_DIR="${STATE_DIR}/backups"
RELEASE_DIR="${APP_ROOT}/release"
SNAPSHOT="${1:-}"

if [[ -z "$SNAPSHOT" ]]; then
  SNAPSHOT="$(find "$SNAP_DIR" -mindepth 2 -maxdepth 2 -type f -name release.tgz -printf '%h\n' 2>/dev/null | sort | tail -n 1 || true)"
fi

if [[ -z "$SNAPSHOT" || ! -f "$SNAPSHOT/release.tgz" ]]; then
  echo "No release snapshot available for rollback." >&2
  exit 2
fi

TMP="$(mktemp -d "${APP_ROOT}/rollback.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$SNAPSHOT/release.tgz" -C "$TMP"

if [[ ! -f "$TMP/infra/compose.yml" ]]; then
  echo "Rollback snapshot is invalid: compose.yml missing." >&2
  exit 3
fi

if [[ -f "$APP_ROOT/infra/.env" ]]; then
  cp "$APP_ROOT/infra/.env" "$TMP/infra/.env"
fi

cd "$TMP/infra"
docker compose --env-file .env -f compose.yml config -q

OLD="${APP_ROOT}/release.failed"
rm -rf "$OLD"
if [[ -d "$RELEASE_DIR" ]]; then mv "$RELEASE_DIR" "$OLD"; fi
mv "$TMP" "$RELEASE_DIR"
trap - EXIT
rm -rf "$OLD"

cd "$RELEASE_DIR/infra"
docker compose --env-file .env -f compose.yml up -d --build

for i in $(seq 1 36); do
  if curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then
    echo "Rollback completed successfully."
    exit 0
  fi
  sleep 5
done

echo "Rollback failed health verification." >&2
exit 4
