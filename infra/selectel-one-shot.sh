#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
ROOT="/opt/chuma"
TMP="/tmp/chuma-install"

[[ "$EUID" -eq 0 ]] || { echo "Run as root"; exit 1; }

echo "[1/7] Preparing..."
rm -rf "$TMP"
mkdir -p "$TMP"

echo "[2/7] Installing prerequisites..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl git tar >/dev/null

echo "[3/7] Installing Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "[4/7] Installing Docker Compose..."
if ! docker compose version >/dev/null 2>&1; then
  mkdir -p /usr/local/lib/docker/cli-plugins
  curl -fsSL "https://github.com/docker/compose/releases/download/v2.40.2/docker-compose-linux-x86_64"     -o /usr/local/lib/docker/cli-plugins/docker-compose
  chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi
docker compose version

echo "[5/7] Getting CHUMA..."
git clone --depth 1 "$REPO" "$TMP/repo"

echo "[6/7] Installing CHUMA..."
if [[ -d "$ROOT" ]]; then
  mv "$ROOT" "${ROOT}.previous-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$ROOT"
cp -a "$TMP/repo/." "$ROOT/"
rm -rf "$TMP"

cd "$ROOT"
bash infra/bootstrap.sh
cd "$ROOT/infra"
docker compose up -d --build

echo "[7/7] Verifying..."
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1:8097/health >/dev/null 2>&1; then
    echo "CHUMA READY"
    if [[ -x "$ROOT/infra/agent-install.sh" ]]; then
      "$ROOT/infra/agent-install.sh" || echo "Agent installation needs final hardening."
    fi
    exit 0
  fi
  sleep 2
done

echo "CHUMA HEALTH CHECK FAILED" >&2
docker compose ps || true
docker compose logs --tail=100 || true
exit 5
