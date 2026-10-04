#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
BACKUP_DIR="${STATE_DIR}/backups"
RELEASE_DIR="${APP_ROOT}/release"
REPO="${CHUMA_UPDATE_REPO:-https://github.com/texx013-boop/CHUMA-IP-FACTORY.git}"
BRANCH="${CHUMA_UPDATE_BRANCH:-main}"
INTERVAL="${CHUMA_UPDATE_INTERVAL:-60}"
LOCK_FILE="${STATE_DIR}/update.lock"
LOG_FILE="${STATE_DIR}/update.log"
ENV_FILE="${APP_ROOT}/infra/.env"
mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"
log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
remote_sha() { git ls-remote "$REPO" "refs/heads/$BRANCH" | awk 'NR==1{print $1}'; }
healthy() { curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; }
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
rollback() {
  local snapshot="$1"
  test -f "$snapshot/release.tgz" || return 1
  local tmp
  tmp="$(mktemp -d "$APP_ROOT/rollback.XXXXXX")"
  tar -xzf "$snapshot/release.tgz" -C "$tmp"
  cp "$ENV_FILE" "$tmp/infra/.env"
  docker compose --env-file "$tmp/infra/.env" -f "$tmp/infra/compose.yml" config -q
  rm -rf "$RELEASE_DIR"
  mv "$tmp" "$RELEASE_DIR"
  docker compose --env-file "$RELEASE_DIR/infra/.env" -f "$RELEASE_DIR/infra/compose.yml" up -d --build
  for i in $(seq 1 36); do
    if healthy; then rm -rf "$tmp"; return 0; fi
    sleep 5
  done
  rm -rf "$tmp"
  return 1
}
log "auto-update started repo=$REPO branch=$BRANCH interval=${INTERVAL}s"
while true; do
  if ! docker info >/dev/null 2>&1; then
    log "docker unavailable"
    sleep "$INTERVAL"
    continue
  fi
  SHA="$(remote_sha || true)"
  if [[ -z "$SHA" ]]; then
    log "unable to read remote revision"
    sleep "$INTERVAL"
    continue
  fi
  CURRENT_SHA=""
  [[ -f "$STATE_DIR/deployed_sha" ]] && CURRENT_SHA="$(cat "$STATE_DIR/deployed_sha" || true)"
  if [[ "$SHA" != "$CURRENT_SHA" ]]; then
    log "new revision detected: $SHA"
    SNAP=""
    if [[ -x "$APP_ROOT/agent/agent-backup.sh" ]]; then SNAP="$("$APP_ROOT/agent/agent-backup.sh" 2>/dev/null || true)"; fi
    TMP="$(mktemp -d "$APP_ROOT/update.XXXXXX")"
    if curl -fsSL --retry 5 --retry-delay 2 "https://github.com/texx013-boop/CHUMA-IP-FACTORY/archive/refs/heads/$BRANCH.tar.gz" -o "$TMP/release.tgz"; then
      mkdir -p "$TMP/source"
      tar -xzf "$TMP/release.tgz" -C "$TMP/source" --strip-components=1
      if [[ -f "$ENV_FILE" ]]; then cp "$ENV_FILE" "$TMP/source/infra/.env"; fi
      if docker compose --env-file "$TMP/source/infra/.env" -f "$TMP/source/infra/compose.yml" config -q; then
        rm -rf "$RELEASE_DIR"
        mv "$TMP/source" "$RELEASE_DIR"
        if docker compose --env-file "$RELEASE_DIR/infra/.env" -f "$RELEASE_DIR/infra/compose.yml" up -d --build; then
          for i in $(seq 1 36); do healthy && break; sleep 5; done
          if healthy; then
            printf '%s\n' "$SHA" > "$STATE_DIR/deployed_sha"
            log "deployment successful: $SHA"
          else
            log "deployment health failed; starting rollback"
            [[ -n "$SNAP" ]] && rollback "$SNAP" && log "rollback successful" || log "rollback failed"
          fi
        else
          log "compose deployment failed"
          [[ -n "$SNAP" ]] && rollback "$SNAP" && log "rollback successful" || true
        fi
      else
        log "release compose validation failed"
      fi
    else
      log "release download failed"
    fi
    rm -rf "$TMP"
  fi
  sleep "$INTERVAL"
done
