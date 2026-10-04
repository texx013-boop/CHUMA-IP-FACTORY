#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
REPO_URL="${REPO_URL:-git@github.com:texx013-boop/CHUMA-IP-FACTORY.git}"
DEPLOY_KEY="${DEPLOY_KEY:-/root/.ssh/chuma_github_deploy_ed25519}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git openssh-client ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker

install -d -m 0700 "$(dirname "$DEPLOY_KEY")"

if [[ ! -f "$DEPLOY_KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -C "chuma-server-deploy" -f "$DEPLOY_KEY"
  chmod 600 "$DEPLOY_KEY"
  chmod 644 "$DEPLOY_KEY.pub"
fi

mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/known_hosts
chmod 600 /root/.ssh/known_hosts
if ! ssh-keygen -F github.com -f /root/.ssh/known_hosts >/dev/null 2>&1; then
  ssh-keyscan -H github.com >> /root/.ssh/known_hosts 2>/dev/null
fi

cat > /root/.ssh/config <<EOF
Host github.com
  HostName github.com
  User git
  IdentityFile $DEPLOY_KEY
  IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config

if ! git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1; then
  echo
  echo "GitHub authorization is not complete."
  echo "Add this PUBLIC deploy key to the private repository:"
  echo
  cat "$DEPLOY_KEY.pub"
  echo
  echo "GitHub: repository Settings -> Deploy keys -> Add deploy key."
  echo "Enable read-only access only."
  echo "Then run this bootstrap script again."
  exit 3
fi

install -d -m 0755 "$APP_ROOT"
if [[ ! -d "$APP_ROOT/.git" ]]; then
  git clone "$REPO_URL" "$APP_ROOT"
else
  git -C "$APP_ROOT" remote set-url origin "$REPO_URL"
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
