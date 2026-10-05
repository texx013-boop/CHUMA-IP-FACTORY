#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

APP_ROOT="$ROOT/app"
mkdir -p "$APP_ROOT/agent" "$APP_ROOT/infra" "$ROOT/work/release"
cp infra/chuma-release.sh "$APP_ROOT/agent/chuma-release.sh"
chmod 0755 "$APP_ROOT/agent/chuma-release.sh"

cat > "$ROOT/work/manifest.env" <<'EOF'
CHUMA_BUNDLE_VERSION=1
CHUMA_PROJECT_ID=CHUMA-IP-FACTORY
CHUMA_RELEASE_ID=test-release-001
CHUMA_COMMIT_SHA=0123456789abcdef0123456789abcdef01234567
EOF
printf 'test payload\n' > "$ROOT/work/release/payload.txt"

tar -czf "$ROOT/good.tar.gz" -C "$ROOT/work" manifest.env release

APP_ROOT="$APP_ROOT" "$APP_ROOT/agent/chuma-release.sh" verify "$ROOT/good.tar.gz" >/dev/null
APP_ROOT="$APP_ROOT" "$APP_ROOT/agent/chuma-release.sh" stage "$ROOT/good.tar.gz" >/dev/null
test -f "$APP_ROOT/control/incoming/test-release-001.tar.gz"
APP_ROOT="$APP_ROOT" "$APP_ROOT/agent/chuma-release.sh" promote "$ROOT/good.tar.gz" >/dev/null
test -f "$APP_ROOT/control/releases/test-release-001/payload.txt"
test "$(cat "$APP_ROOT/control/state/handoff_sha")" = "0123456789abcdef0123456789abcdef01234567"

mkdir -p "$ROOT/bad/release"
cat > "$ROOT/bad/manifest.env" <<'EOF'
CHUMA_BUNDLE_VERSION=1
CHUMA_PROJECT_ID=CHUMA-IP-FACTORY
CHUMA_RELEASE_ID=bad-release
CHUMA_COMMIT_SHA=0123456789abcdef0123456789abcdef01234567
EOF
printf 'SECRET=must-not-pass\n' > "$ROOT/bad/release/.env"
tar -czf "$ROOT/bad.tar.gz" -C "$ROOT/bad" manifest.env release
if APP_ROOT="$APP_ROOT" "$APP_ROOT/agent/chuma-release.sh" verify "$ROOT/bad.tar.gz" >/dev/null 2>&1; then
  echo "bad bundle was accepted" >&2
  exit 1
fi

echo "CHUMA release handoff test: OK"
