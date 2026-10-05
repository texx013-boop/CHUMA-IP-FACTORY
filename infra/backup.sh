#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/chuma-postgres-$STAMP.sql.gz"
TMP="$FILE.tmp"

cleanup() {
  rm -f "$TMP"
}
trap cleanup EXIT INT TERM

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' | gzip -9 > "$TMP"
test -s "$TMP"
mv -f "$TMP" "$FILE"
sha256sum "$FILE" > "$FILE.sha256"
chmod 600 "$FILE" "$FILE.sha256"

find "$BACKUP_DIR" -type f \( -name 'chuma-postgres-*.sql.gz' -o -name 'chuma-postgres-*.sql.gz.sha256' \) -mtime +"$RETENTION_DAYS" -delete

echo "backup created: $FILE"
