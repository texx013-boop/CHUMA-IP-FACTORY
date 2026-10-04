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
COMPOSE_RUN="${APP_ROOT}/infra/compose-run.sh"

mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
compose() { "$COMPOSE_RUN" --env-file "$1" -f "$2" "${@:3}"; }
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
  if [[ -z "$SHA" ]]; then
    log "unable to read remote revision"
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
  SNAP=""
  if [[ -x "$APP_ROOT/agent/agent-backup.sh" ]]; then
    SNAP="$("$APP_ROOT/agent/agent-backup.sh" 2>/dev/null || true)"
  fi

  TMP="$(mktemp -d "$APP_ROOT/update.XXXXXX")"

  if ! curl -fsSL --retry 5 --retry-delay 2       "https://github.com/texx013-boop/CHUMA-IP-FACTORY/archive/refs/heads/$BRANCH.tar.gz"       -o "$TMP/release.tgz"; then
    log "release download failed"
    sleep "$INTERVAL"
    continue
  fi

  mkdir -p "$TMP/source"
  if ! tar -xzf "$TMP/release.tgz" -C "$TMP/source" --strip-components=1; then
    log "release archive extraction failed"
    sleep "$INTERVAL"
    continue
  fi

  for required in Dockerfile run.py infra/compose.yml infra/compose-run.sh; do
    if [[ ! -f "$TMP/source/$required" ]]; then
      log "release rejected: missing $required"
      continue 2
    fi
  done

  cp "$ENV_FILE" "$TMP/source/infra/.env"

  if ! "$TMP/source/infra/compose-run.sh" --env-file "$TMP/source/infra/.env"       -f "$TMP/source/infra/compose.yml" config -q; then
    log "release rejected: compose validation failed"
    sleep "$INTERVAL"
    continue
  fi

  rm -rf "$PREVIOUS_DIR"
  if [[ -d "$RELEASE_DIR" ]]; then
    mv "$RELEASE_DIR" "$PREVIOUS_DIR"
  fi
  mv "$TMP/source" "$RELEASE_DIR"

  if "$RELEASE_DIR/infra/compose-run.sh" --env-file "$RELEASE_DIR/infra/.env"       -f "$RELEASE_DIR/infra/compose.yml" up -d --build; then
    READY=0
    for i in $(seq 1 36); do
      if healthy; then READY=1; break; fi
      sleep 5
    done

    if [[ "$READY" -eq 1 ]]; then
      if [[ -x "$RELEASE_DIR/infra/agent-install.sh" ]]; then
        "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1 || log "agent refresh failed"
      fi
      printf '%s\n' "$SHA" > "$STATE_DIR/deployed_sha"
      rm -rf "$PREVIOUS_DIR"
      log "deployment successful: $SHA"
    else
      log "deployment health failed; restoring previous release"
      "$RELEASE_DIR/infra/compose-run.sh" --env-file "$RELEASE_DIR/infra/.env"         -f "$RELEASE_DIR/infra/compose.yml" down >/dev/null 2>&1 || true
      rm -rf "$RELEASE_DIR"
      if [[ -d "$PREVIOUS_DIR" ]]; then
        mv "$PREVIOUS_DIR" "$RELEASE_DIR"
        "$RELEASE_DIR/infra/compose-run.sh" --env-file "$RELEASE_DIR/infra/.env"           -f "$RELEASE_DIR/infra/compose.yml" up -d --build >/dev/null 2>&1 || true
        log "previous release restore attempted"
      else
        log "no previous release available"
      fi
    fi
  else
    log "compose deployment failed; restoring previous release"
    rm -rf "$RELEASE_DIR"
    if [[ -d "$PREVIOUS_DIR" ]]; then
      mv "$PREVIOUS_DIR" "$RELEASE_DIR"
      "$RELEASE_DIR/infra/compose-run.sh" --env-file "$RELEASE_DIR/infra/.env"         -f "$RELEASE_DIR/infra/compose.yml" up -d --build >/dev/null 2>&1 || true
      log "previous release restore attempted"
    fi
  fi

  rm -rf "$TMP"
  sleep "$INTERVAL"
done
