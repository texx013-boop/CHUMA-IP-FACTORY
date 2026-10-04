#!/usr/bin/env bash
set -Eeuo pipefail

REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
ROOT="/opt/chuma"
TMP="/tmp/chuma-install"

trap 'echo "CHUMA INSTALL FAILED. See the last error above."; exit 1' ERR

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi

echo "[1/6] Preparing server..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git >/dev/null

echo "[2/6] Preparing Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "[3/6] Preparing Compose..."
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  mkdir -p /usr/local/bin
  curl -fL --retry 3 --retry-delay 2 \
    "https://github.com/docker/compose/releases/download/v2.40.2/docker-compose-linux-x86_64" \
    -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  COMPOSE=(/usr/local/bin/docker-compose)
fi
"${COMPOSE[@]}" version

echo "[4/6] Installing CHUMA..."
rm -rf "$TMP"
git clone --depth 1 "$REPO" "$TMP"
if [[ -d "$ROOT" ]]; then
  mv "$ROOT" "${ROOT}.previous-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$ROOT"
cp -a "$TMP"/. "$ROOT"/
rm -rf "$TMP"

cd "$ROOT"
bash infra/bootstrap.sh
cd "$ROOT/infra"
"${COMPOSE[@]}" up -d --build

echo "[5/6] Verifying CHUMA..."
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1:8097/health >/dev/null 2>&1; then
    echo "CHUMA READY"
    break
  fi
  sleep 2
done

if ! curl -fsS --max-time 5 http://127.0.0.1:8097/health >/dev/null 2>&1; then
  echo "CHUMA HEALTH CHECK FAILED"
  "${COMPOSE[@]}" ps || true
  "${COMPOSE[@]}" logs --tail=100 || true
  exit 5
fi

echo "[6/6] Installing autonomous agent..."
if [[ -x "$ROOT/infra/agent-install.sh" ]]; then
  "$ROOT/infra/agent-install.sh" || echo "Agent install deferred; CHUMA itself is running."
fi

echo
echo "================================"
echo "CHUMA INSTALLATION COMPLETE"
echo "================================"
