#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
STATE_DIR="${APP_ROOT}/agent"
BACKUP_DIR="${STATE_DIR}/backups"
RELEASE_DIR="${APP_ROOT}/release"
PREVIOUS_DIR="${APP_ROOT}/release.previous"
REPO="${CHUMA_UPDATE_REPO:-git@github.com:texx013-boop/CHUMA-IP-FACTORY.git}"
BRANCH="${CHUMA_UPDATE_BRANCH:-main}"
INTERVAL="${CHUMA_UPDATE_INTERVAL:-60}"
AUTO_UPDATE="${CHUMA_AUTO_UPDATE:-true}"
# GitHub CI is advisory by default; set true for a strict release gate.
REQUIRE_CI_GREEN="${CHUMA_REQUIRE_CI_GREEN:-false}"
GITHUB_KEY="${GITHUB_DEPLOY_KEY:-$STATE_DIR/github_deploy_ed25519}"
KNOWN_HOSTS="${GITHUB_KNOWN_HOSTS:-$STATE_DIR/github_known_hosts}"
LOCK_FILE="${STATE_DIR}/update.lock"
LOG_FILE="${STATE_DIR}/update.log"
ENV_FILE="${APP_ROOT}/infra/.env"

mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
compose() { "$APP_ROOT/infra/compose-run.sh" --env-file "$1" -f "$2" "${@:3}"; }
GIT_SSH_COMMAND="ssh -i $GITHUB_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN_HOSTS"
git_env=(env GIT_SSH_COMMAND="$GIT_SSH_COMMAND")
remote_sha() { "${git_env[@]}" git ls-remote "$REPO" "refs/heads/$BRANCH" | awk 'NR==1{print $1}'; }
ci_green(){
  local sha="$1" payload
  payload="$(curl -fsS --max-time 15 "https://api.github.com/repos/texx013-boop/CHUMA-IP-FACTORY/actions/runs?head_sha=$sha&per_page=50" 2>/dev/null)" || return 1
  python3 - "$sha" "$payload" <<'PY'
import json,sys
sha=sys.argv[1]
data=json.loads(sys.argv[2])
runs=[r for r in data.get("workflow_runs",[]) if r.get("head_sha")==sha]
required={"CHUMA IP FACTORY CI","CHUMA Server Handoff"}
for name in required:
    matches=[r for r in runs if r.get("name")==name]
    if not matches or not any(r.get("status")=="completed" and r.get("conclusion")=="success" for r in matches):
        raise SystemExit(1)
raise SystemExit(0)
PY
}
healthy() {
  curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1 &&
  curl -fsS --max-time 5 http://127.0.0.1/ready >/dev/null 2>&1
}

process_handoff() {
  local bundle=""
  local found=0
  shopt -s nullglob
  for candidate in "$APP_ROOT/control/incoming/"*.tar.gz; do
    bundle="$candidate"
    found=1
    break
  done
  shopt -u nullglob
  [[ "$found" -eq 1 ]] || return 1

  log "local release handoff detected: $bundle"
  if ! "$APP_ROOT/agent/chuma-release.sh" verify "$bundle" >/dev/null; then
    log "local release rejected during verification: $bundle"
    return 0
  fi

  local release_path=""
  if ! release_path="$("$APP_ROOT/agent/chuma-release.sh" promote "$bundle" | tail -n 1)"; then
    log "local release promotion failed: $bundle"
    return 0
  fi
  [[ -d "$release_path" ]] || {
    log "local release promotion produced invalid path: $release_path"
    return 0
  }

  if [[ ! -f "$ENV_FILE" ]]; then
    log "local release blocked: deployment environment file is missing"
    rm -rf "$release_path"
    return 0
  fi
  mkdir -p "$release_path/infra"
  cp "$ENV_FILE" "$release_path/infra/.env"
  chmod 600 "$release_path/infra/.env"

  if ! "$release_path/infra/compose-run.sh" --env-file "$release_path/infra/.env" -f "$release_path/infra/compose.yml" config -q; then
    log "local release rejected: compose validation failed"
    rm -rf "$release_path"
    return 0
  fi

  if [[ -x "$APP_ROOT/agent/agent-backup.sh" ]]; then
    local snap=""
    if ! snap="$("$APP_ROOT/agent/agent-backup.sh" 2>/dev/null)"; then
      log "local release blocked: pre-update snapshot failed"
      rm -rf "$release_path"
      return 0
    fi
    log "local release pre-update snapshot: $snap"
  fi

  rm -rf "$PREVIOUS_DIR"
  if [[ -d "$RELEASE_DIR" ]]; then mv "$RELEASE_DIR" "$PREVIOUS_DIR"; fi
  mv "$release_path" "$RELEASE_DIR"

  local deployed_ok=0
  if compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build; then
    for i in $(seq 1 36); do
      if healthy; then deployed_ok=1; break; fi
      sleep 5
    done
  fi

  if [[ "$deployed_ok" -eq 1 ]]; then
    if ! "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1; then
      log "local release agent refresh failed; deployment is not accepted"
      deployed_ok=0
    fi
  fi

  if [[ "$deployed_ok" -eq 1 ]]; then
    local handoff_sha=""
    [[ -f "$STATE_DIR/handoff_sha" ]] && handoff_sha="$(cat "$STATE_DIR/handoff_sha" || true)"
    if [[ ! "$handoff_sha" =~ ^[0-9a-f]{40}$ ]]; then
      log "local release rejected: promoted SHA is invalid"
      deployed_ok=0
    else
      printf '%s\n' "$handoff_sha" > "$STATE_DIR/deployed_sha"
      chmod 600 "$STATE_DIR/deployed_sha"
      rm -rf "$PREVIOUS_DIR"
      rm -f "$bundle"
      log "local release deployment successful: $handoff_sha"
    fi
  fi

  if [[ "$deployed_ok" -ne 1 ]]; then
    log "local release deployment failed; restoring previous release"
    compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" down >/dev/null 2>&1 || true
    rm -rf "$RELEASE_DIR"
    if [[ -d "$PREVIOUS_DIR" ]]; then
      mv "$PREVIOUS_DIR" "$RELEASE_DIR"
      if "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1 &&
         compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build >/dev/null 2>&1 &&
         "$RELEASE_DIR/infra/agent-verify.sh" >/dev/null 2>&1; then
        log "previous release restored after local handoff failure"
      else
        log "previous release restore failed after local handoff failure"
      fi
    else
      log "no previous release available after local handoff failure"
    fi
    rm -rf "$release_path" 2>/dev/null || true
  fi

  return 0
}

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
log "auto-update started repo=$REPO branch=$BRANCH interval=${INTERVAL}s enabled=$AUTO_UPDATE"

while true; do
  if [[ "$AUTO_UPDATE" != "true" ]]; then sleep "$INTERVAL"; continue; fi
  if process_handoff; then sleep "$INTERVAL"; continue; fi
  if ! docker info >/dev/null 2>&1; then log "docker unavailable"; sleep "$INTERVAL"; continue; fi
  if [[ ! -r "$GITHUB_KEY" || ! -r "$KNOWN_HOSTS" ]]; then
    log "update blocked: GitHub SSH identity/known_hosts missing"
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
  if [[ "$SHA" == "$CURRENT_SHA" ]]; then sleep "$INTERVAL"; continue; fi

  log "new revision detected: $SHA"
  if [[ "$REQUIRE_CI_GREEN" == "true" ]]; then
    if ! ci_green "$SHA"; then
      log "update blocked by explicit CI policy: required GitHub validation is not green for $SHA"
      sleep "$INTERVAL"
      continue
    fi
  else
    log "GitHub CI is advisory; proceeding with server-side release verification for $SHA"
  fi
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

  if ! "${git_env[@]}" git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$TMP/repo"; then
    log "private repository access failed"
    trap - EXIT; cleanup; sleep "$INTERVAL"; continue
  fi

  CLONED_SHA="$(git -C "$TMP/repo" rev-parse HEAD)"
  if [[ "$CLONED_SHA" != "$SHA" ]]; then
    log "repository changed during fetch; retrying on next cycle"
    trap - EXIT; cleanup; sleep "$INTERVAL"; continue
  fi

  mkdir -p "$TMP/source"
  if ! git -C "$TMP/repo" archive --format=tar HEAD -o "$TMP/release.tar" 2>"$TMP/archive.err"; then
    ARCHIVE_ERR="$(tr '\n' ' ' < "$TMP/archive.err" 2>/dev/null || true)"
    log "release archive creation failed: ${ARCHIVE_ERR:-unknown error}"
    if ! tar --exclude=.git -cf "$TMP/release.tar" -C "$TMP/repo" . 2>"$TMP/archive-fallback.err"; then
      FALLBACK_ERR="$(tr '\n' ' ' < "$TMP/archive-fallback.err" 2>/dev/null || true)"
      log "release archive fallback failed: ${FALLBACK_ERR:-unknown error}"
      trap - EXIT; cleanup; sleep "$INTERVAL"; continue
    fi
    log "release archive fallback succeeded"
  fi
  if ! tar -xf "$TMP/release.tar" -C "$TMP/source"; then
    log "release archive extraction failed"
    trap - EXIT; cleanup; sleep "$INTERVAL"; continue
  fi

  cp -a "$TMP/source" "$TMP/source.checked"
  if find "$TMP/source.checked" -type f \( -name '.env' -o -name '*.pem' -o -name '*.key' \) -print -quit | grep -q .; then
    log "release rejected: secret-like files present"
    trap - EXIT; cleanup; sleep "$INTERVAL"; continue
  fi

  for required in Dockerfile run.py infra/compose.yml infra/compose-run.sh; do
    [[ -f "$TMP/source/$required" ]] || { log "release rejected: missing $required"; trap - EXIT; cleanup; sleep "$INTERVAL"; continue 2; }
  done

  chmod +x "$TMP/source/infra/compose-run.sh"
  cp "$ENV_FILE" "$TMP/source/infra/.env"
  chmod 600 "$TMP/source/infra/.env"

  if ! "$TMP/source/infra/compose-run.sh" --env-file "$TMP/source/infra/.env" -f "$TMP/source/infra/compose.yml" config -q; then
    log "release rejected: compose validation failed"
    trap - EXIT; cleanup; sleep "$INTERVAL"; continue
  fi

  rm -rf "$PREVIOUS_DIR"
  if [[ -d "$RELEASE_DIR" ]]; then mv "$RELEASE_DIR" "$PREVIOUS_DIR"; fi
  mv "$TMP/source" "$RELEASE_DIR"

  deployed_ok=0
  if compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build; then
    for i in $(seq 1 36); do if healthy; then deployed_ok=1; break; fi; sleep 5; done
  fi

  if [[ "$deployed_ok" -eq 1 ]]; then
    if ! "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1; then
      log "agent refresh failed; deployment is not accepted"
      deployed_ok=0
    fi
  fi

  if [[ "$deployed_ok" -eq 1 ]]; then
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
      if "$RELEASE_DIR/infra/agent-install.sh" >/dev/null 2>&1 &&          compose "$RELEASE_DIR/infra/.env" "$RELEASE_DIR/infra/compose.yml" up -d --build >/dev/null 2>&1 &&          "$RELEASE_DIR/infra/agent-verify.sh" >/dev/null 2>&1; then
        log "previous release restored and healthy"
      else
        log "previous release restore failed or health check failed"
      fi
    else
      log "no previous release available; manual recovery may be required"
    fi
  fi

  trap - EXIT
  cleanup
  sleep "$INTERVAL"
done
