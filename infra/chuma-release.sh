#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
INCOMING_DIR="$CONTROL_ROOT/incoming"
STAGING_DIR="$CONTROL_ROOT/staging"
RELEASES_DIR="$CONTROL_ROOT/releases"
STATE_DIR="$CONTROL_ROOT/state"
LOG_FILE="$STATE_DIR/control.log"
LOCK_FILE="$STATE_DIR/release.lock"

mkdir -p "$INCOMING_DIR" "$STAGING_DIR" "$RELEASES_DIR" "$STATE_DIR"
chmod 700 "$INCOMING_DIR" "$STAGING_DIR" "$RELEASES_DIR" "$STATE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"; }
die() { log "release rejected: $*"; exit 1; }

usage() {
  cat <<'EOF'
CHUMA RELEASE HANDOFF
Usage:
  chuma-release.sh verify <bundle.tar.gz>
  chuma-release.sh stage <bundle.tar.gz>
  chuma-release.sh promote <bundle.tar.gz>
EOF
}

require_safe_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || die "unsafe identifier"
}

manifest_value() {
  local manifest="$1" key="$2"
  awk -F= -v wanted="$key" '$1 == wanted { value=$2; sub(/\\r$/, "", value); print value; exit }' "$manifest"
}

verify_bundle() {
  local bundle="$1"
  [[ -f "$bundle" ]] || die "bundle not found"
  [[ "$bundle" != *$'\n'* && "$bundle" != *$'\r'* ]] || die "unsafe bundle path"

  local tmp
  tmp="$(mktemp -d "$STAGING_DIR/verify.XXXXXX")"
  chmod 700 "$tmp"
  trap 'rm -rf "$tmp"' RETURN

  tar -tzf "$bundle" >/dev/null || die "invalid tar.gz bundle"
  tar -tvzf "$bundle" | awk 'substr($1,1,1) == "l" || substr($1,1,1) == "h" { found=1; exit } END { exit found ? 1 : 0 }' || die "links are not allowed in bundle"
  local entries
  entries="$(tar -tzf "$bundle")"
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    [[ "$entry" != /* && "$entry" != *../* && "$entry" != ../* ]] || die "path traversal in bundle"
    [[ "$entry" == "manifest.env" || "$entry" == "manifest.sha256" || "$entry" == release/* ]] || die "unexpected path in bundle"
    if [[ "$entry" != "manifest.env" && "$entry" != "manifest.sha256" ]]; then
      [[ "$entry" != *".env"* && "$entry" != *.pem && "$entry" != *.key && "$entry" != *.p12 && "$entry" != *.pfx ]] || die "secret-like file in bundle"
    fi
  done <<< "$entries"

  tar -xzf "$bundle" -C "$tmp"
  [[ -f "$tmp/manifest.env" ]] || die "manifest.env missing"
  [[ -d "$tmp/release" ]] || die "release directory missing"

  local bundle_version project_id release_id commit_sha
  bundle_version="$(manifest_value "$tmp/manifest.env" CHUMA_BUNDLE_VERSION)"
  project_id="$(manifest_value "$tmp/manifest.env" CHUMA_PROJECT_ID)"
  release_id="$(manifest_value "$tmp/manifest.env" CHUMA_RELEASE_ID)"
  commit_sha="$(manifest_value "$tmp/manifest.env" CHUMA_COMMIT_SHA)"
  [[ "$bundle_version" == "1" ]] || die "unsupported bundle version"
  require_safe_name "$project_id"
  require_safe_name "$release_id"
  [[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]] || die "invalid commit SHA"
  [[ "$project_id" == "CHUMA-IP-FACTORY" ]] || die "unexpected project id"

  [[ -f "$tmp/release/Dockerfile" || -f "$tmp/release/infra/compose.yml" ]] || die "release payload is incomplete"

  if [[ -f "$tmp/manifest.sha256" ]]; then
    (cd "$tmp" && sha256sum -c manifest.sha256 >/dev/null) || die "manifest checksum verification failed"
  fi

  printf 'bundle.ok=true\n'
  printf 'project=%s\n' "$project_id"
  printf 'release=%s\n' "$release_id"
  printf 'commit=%s\n' "$commit_sha"
}

stage_bundle() {
  local bundle="$1"
  verify_bundle "$bundle" >/dev/null
  local release_id
  release_id="$(tar -xOzf "$bundle" manifest.env | awk -F= '$1=="CHUMA_RELEASE_ID" && $2 ~ /^[A-Za-z0-9._-]+$/ {print $2; exit}')"
  [[ -n "$release_id" ]] || die "invalid release id"
  local target="$INCOMING_DIR/$release_id.tar.gz"
  install -m 0600 "$bundle" "$target"
  log "release staged: $release_id"
  printf '%s\n' "$target"
}

promote_bundle() {
  local bundle="$1"
  verify_bundle "$bundle" >/dev/null
  exec 9>"$LOCK_FILE"
  flock -n 9 || die "another release operation is active"

  local tmp release_id commit_sha
  tmp="$(mktemp -d "$STAGING_DIR/promote.XXXXXX")"
  chmod 700 "$tmp"
  trap 'rm -rf "$tmp"' EXIT
  tar -xzf "$bundle" -C "$tmp"

  release_id="$(manifest_value "$tmp/manifest.env" CHUMA_RELEASE_ID)"
  commit_sha="$(manifest_value "$tmp/manifest.env" CHUMA_COMMIT_SHA)"
  require_safe_name "$release_id"
  [[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]] || die "invalid promotion SHA"
  local target="$RELEASES_DIR/$release_id"
  [[ ! -e "$target" ]] || die "release already exists"

  chmod -R go-rwx "$tmp/release" 2>/dev/null || true
  mv "$tmp/release" "$target"
  printf '%s\n' "$commit_sha" > "$STATE_DIR/handoff_sha"
  printf '%s\n' "$release_id" > "$STATE_DIR/handoff_release"
  chmod 600 "$STATE_DIR/handoff_sha" "$STATE_DIR/handoff_release"
  log "release promoted: $release_id sha=$commit_sha"
  printf '%s\n' "$target"
  trap - EXIT
  rm -rf "$tmp"
}

case "${1:-}" in
  verify) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; verify_bundle "$2" ;;
  stage) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; stage_bundle "$2" ;;
  promote) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; promote_bundle "$2" ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 64 ;;
esac
