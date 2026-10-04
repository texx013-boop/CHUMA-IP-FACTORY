#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/infra/backups}"

latest="$(find "$BACKUP_DIR" -type f -name 'chuma-postgres-*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1{print $2}')"
[[ -n "$latest" && -s "$latest" ]] || { echo "No usable PostgreSQL backup found." >&2; exit 2; }

gzip -t "$latest"
sha256sum "$latest" > "$latest.sha256"
echo "Backup integrity: OK"
echo "$latest"
