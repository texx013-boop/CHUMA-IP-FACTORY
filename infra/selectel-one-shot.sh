#!/usr/bin/env bash
set -Eeuo pipefail

REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
ROOT="/opt/chuma"
TMP="/tmp/chuma-install"

trap 'echo "CHUMA INSTALL FAILED. Check the error above."; exit 1' ERR

[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }

export DEBIAN_FRONTEND=noninteractive

echo "[1/7] Preparing server..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl git openssl >/dev/null

echo "[2/7] Preparing Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker info >/dev/null

echo "[3/7] Preparing Compose..."
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  mkdir -p /usr/local/bin
  curl -fL --retry 5 --retry-delay 2     "https://github.com/docker/compose/releases/download/v2.40.2/docker-compose-linux-x86_64"     -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  COMPOSE=(/usr/local/bin/docker-compose)
fi
"${COMPOSE[@]}" version

echo "[4/7] Installing latest CHUMA..."
rm -rf "$TMP"
git clone --depth 1 "$REPO" "$TMP"
if [[ -d "$ROOT" ]]; then
  mv "$ROOT" "${ROOT}.previous-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$ROOT"
cp -a "$TMP"/. "$ROOT"/
rm -rf "$TMP"

echo "[5/7] Bootstrapping server..."
cd "$ROOT"
bash infra/bootstrap.sh
cd "$ROOT/infra"

echo "[6/7] Building and starting CHUMA..."
"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps

echo "[7/7] Verifying..."
READY=0
for i in $(seq 1 90); do
  if curl -fsS --max-time 5 http://127.0.0.1:8097/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -ne 1 ]]; then
  echo "CHUMA HEALTH CHECK FAILED"
  "${COMPOSE[@]}" ps || true
  "${COMPOSE[@]}" logs --tail=120 || true
  exit 5
fi

if [[ -x "$ROOT/infra/agent-install.sh" ]]; then
  "$ROOT/infra/agent-install.sh"
fi

echo
echo "========================================"
echo "CHUMA SERVER READY"
echo "========================================"
echo "Local health: http://127.0.0.1:8097/health"
echo "Web UI:       http://$(hostname -I | awk '{print $1}')/"
echo "Control root: $ROOT"
echo "Agent:        systemctl status chuma-agent"
echo "========================================"
