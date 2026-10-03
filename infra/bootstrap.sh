#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
REPO_URL="${REPO_URL:-https://github.com/texx013-boop/CHUMA-IP-FACTORY.git}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker

install -d -m 0755 "$APP_ROOT"
if [[ ! -d "$APP_ROOT/.git" ]]; then
  git clone "$REPO_URL" "$APP_ROOT"
else
  git -C "$APP_ROOT" fetch --prune origin
  git -C "$APP_ROOT" reset --hard origin/main
fi

cd "$APP_ROOT/infra"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created $APP_ROOT/infra/.env. Fill the required values before starting."
  exit 2
fi

chmod 600 .env

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

docker compose pull
docker compose build --pull
docker compose up -d

docker compose ps
