#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
BACKUP_DIR="${STATE_DIR}/backups"
RELEASE_DIR="${APP_ROOT}/release"
PREVIOUS_DIR="${APP_ROOT}/release.previous"
REPO="${CHUMA_UPDATE_REPO:-https://github.com/texx013-boop/CHUMA-IP-FACTORY.git}"
BRANCH="${CHUMA_UPDATE_BRANCH:-main}"
INTERVAL="${CHUMA_UPDATE_INTERVAL:-60}"
AUTO_UPDATE="${CHUMA_AUTO_UPDATE:-true}"
LOCK_FILE="${STATE_DIR}/update.lock"
LOG_FILE="${STATE_DIR}/update.log"
ENV_FILE="${APP_ROOT}/infra/.env"

mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
compose() { "$APP_ROOT/infra/compose-run.sh" --env-file "$1" -f "$2" "${@:3}"; }
remote_sha() { git ls-remote "$REPO" "refs/heads/$BRANCH" | awk 'NR==1{print $1}'; }
healthy() { curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; }

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
log "auto-update started repo=$REPO branch=$BRANCH interval=${INTERVAL}s enabled=$AUTO_UPDATE"

while true; do
  if [[ "$AUTO_UPDATE" != "true" ]]; then
    sleep "$INTERVAL"
    continue
  fi

  if ! docker info >/dev/null 2>&1; then
    log "docker unavailable"
    sleep "$INTERVAL"
    continue
  fi

  SHA="$(remote_sha || true)"
  if [[ -z "$SHA" || ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
    log "unable to read valid remote revision"
    sleep "$INTERVAL"
    continue
  fi

  CURRENT_SHA=""
  [[ -f "$STATE_DIR/deployed_sha" ]] && CURRENT_SHA="$(cat "$STATE_DIR/deployed_sha" || true)"
  if [[ "$SHA" == "$CURRENT_SHA" ]]; then
    sleep "$INTERVAL"
    continue
  fi

  log "new revision detected: $SHA"
  if [[ ! -f "$ENV_FILE" ]]; then
    log "update blocked: deployment environment file is missing"
    sleep "$INTERVAL"
    continue
  fi

  if [[ -x "$APP_ROOT/agent/agent-backup.sh" ]]; then
    if ! SNAP="$("$APP_ROOT/agent/agent-backup.sh" 2>/dev/null)"; then
      log "update blocked: pre-update snapshot failed"
      sleep "$INTERVAL"
      continue
    fi
    log "pre-update snapshot: $SNAP"
  fi

  TMP="$(mktemp -d "$APP_ROOT/update.XXXXXX")"
  cleanup() { rm -rf "$TMP"; }
  trap cleanup EXIT

  # Pin the download to the exact commit observed by ls-remote.
  if ! curl -fsSL --retry 5 --retry-delay 2 \
      "https://github.com/texx013-boop/CHUMA-IP-FACTORY/archive/$SHA.tar.gz" \
      -o "$TMP/release.tgz"; then
    log "release download failed"
    trap - EXIT
    cleanup
    sleep "$INTERVAL"
    continue
  fi

  mkdir -p "$TMP/source"
  if ! tar -xzf "$TMP/release.tgz" -C "$TMP/source" --strip-components=1; then
    log "release archive extraction failed"
    trap - EXIT
    cleanup
    sleep "$INTERVAL"
    continue
  fi

  # Reject archives containing path traversal or absolute paths before deployment.
  if tar -tzf "$TMP/release.tgz" | awk 'BEGIN{bad=0} /^\// || /(^|\/)\.\.(\/|$)/ {bad=1; print; next} END{exit bad}'; then
    :
  else
    log "release rejected: unsafe archive path"
    trap - EXIT
    cleanup
    sleep "$INTERVAL"
    continue
  fi

  for required in Dockerfile run.py infra/compose.yml infra/compose-run.sh; do
    if [[ ! -f "$TMP/source/$required" ]]; then
      log "release rejected: missing $required"
      trap - EXIT
      cleanup
      sleep "$INTERVAL"
      continue 2
    fi
  done

  cp "$ENV_FILE" "$TMP/source/infra/.env"
  chmod 600 "$TMP/source/infra/.env"

  if ! "$TMP/source/infra/compose-run.sh" --env-file "$TMP/source/infra/.env" \
      -f "$TMP/source/infra/compose.yml" config -q; then
    log "release rejected: compose validation failed"
    trap - EXIT
    cleanup
    sleep "$INTERVAL"
    continue
  fi

  rm -rf "$PREVIOUS_DIR"
  if [[ -d "$RELEASE_DIR" ]]; then
    mv "$RELEASE_DIR" "$PREVIOUS_DIR"
  fi
  mv "$TMP/source" "$RELEASE_DIR"

  deployed_ok=0
  if compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build; then
    for i in $(seq 1 36); do
      if healthy; then deployed_ok=1; break; fi
      sleep 5
    done
  fi

  if [[ "$deployed_ok" -eq 1 ]]; then
    if [[ -x "$RELEASE_DIR/infra/agent-install.sh" ]]; then
      "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1 || log "agent refresh failed"
    fi
    printf '%s\n' "$SHA" > "$STATE_DIR/deployed_sha"
    chmod 600 "$STATE_DIR/deployed_sha"
    rm -rf "$PREVIOUS_DIR"
    log "deployment successful: $SHA"
  else
    log "deployment failed; restoring previous release"
    compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" down >/dev/null 2>&1 || true
    rm -rf "$RELEASE_DIR"
    if [[ -d "$PREVIOUS_DIR" ]]; then
      mv "$PREVIOUS_DIR" "$RELEASE_DIR"
      if compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build >/dev/null 2>&1; then
        for i in $(seq 1 36); do
          if healthy; then
            log "previous release restored and healthy"
            break
          fi
          sleep 5
        done
      fi
    else
      log "no previous release available; manual recovery may be required"
    fi
  fi

  trap - EXIT
  cleanup
  sleep "$INTERVAL"
done
