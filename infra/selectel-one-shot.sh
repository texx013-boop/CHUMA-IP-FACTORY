#!/usr/bin/env bash
set -Eeuo pipefail

REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
ROOT="/opt/chuma"
TMP="/tmp/chuma-install"

trap 'echo "CHUMA INSTALL FAILED. Check the error above."; exit 1' ERR

[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }

export DEBIAN_FRONTEND=noninteractive
# Never wait indefinitely on a network/provider operation.
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="ssh -o ConnectTimeout=15 -o BatchMode=yes"

echo "[1/7] Preparing server..."
apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update
apt-get install -y ca-certificates curl git openssl

echo "[2/7] Preparing Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fL --connect-timeout 15 --max-time 180 --retry 3 --retry-delay 2 https://get.docker.com | sh
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
  curl -fL --connect-timeout 15 --max-time 180 --retry 5 --retry-delay 2     "https://github.com/docker/compose/releases/download/v2.40.2/docker-compose-linux-x86_64"     -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  COMPOSE=(/usr/local/bin/docker-compose)
fi
"${COMPOSE[@]}" version

echo "[4/7] Installing latest CHUMA..."
rm -rf "$TMP"
git -c http.connectTimeout=15 -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 clone --depth 1 --single-branch "$REPO" "$TMP"
if [[ -d "$ROOT" ]]; then
  PREVIOUS_ROOT="${ROOT}.previous-$(date +%Y%m%d-%H%M%S)"
  mv "$ROOT" "$PREVIOUS_ROOT"
else
  PREVIOUS_ROOT=""
fi
mkdir -p "$ROOT"
cp -a "$TMP"/. "$ROOT"/
if [[ -n "$PREVIOUS_ROOT" && -f "$PREVIOUS_ROOT/infra/.env" ]]; then
  cp "$PREVIOUS_ROOT/infra/.env" "$ROOT/infra/.env"
  chmod 600 "$ROOT/infra/.env"
fi
rm -rf "$TMP"

echo "[5/7] Bootstrapping server..."
cd "$ROOT"
bash infra/bootstrap.sh
PUBLIC_IP="${CHUMA_PUBLIC_IP:-161.104.32.15}"
CHUMA_DOMAIN=":80"
sed -i "s#^CHUMA_DOMAIN=.*#CHUMA_DOMAIN=$CHUMA_DOMAIN#" "$ROOT/infra/.env"

echo "[6/7] Building and starting CHUMA..."
cd "$ROOT/infra"
"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps

echo "[7/7] Verifying..."
READY=0
for i in $(seq 1 90); do
  if curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -ne 1 ]]; then
  echo "CHUMA WEB HEALTH CHECK FAILED"
  "${COMPOSE[@]}" ps || true
  echo "--- proxy logs ---"
  "${COMPOSE[@]}" logs --tail=80 proxy || true
  echo "--- app logs ---"
  "${COMPOSE[@]}" logs --tail=80 app || true
  exit 5
fi

if [[ -x "$ROOT/infra/agent-install.sh" ]]; then
  "$ROOT/infra/agent-install.sh"
fi

echo
echo "========================================"
echo "CHUMA SERVER READY"
echo "========================================"
echo "Web UI:       http://$PUBLIC_IP/"
echo "Health:       http://$PUBLIC_IP/health"
echo "Control root: $ROOT"
echo "Agent:        systemctl status chuma-agent"
echo "========================================"
