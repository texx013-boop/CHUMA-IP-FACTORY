#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
DEPLOY_USER="${DEPLOY_USER:-chuma-deploy}"
DEPLOY_PUBLIC_KEY="${DEPLOY_PUBLIC_KEY:-}"
GITHUB_KEY="${GITHUB_DEPLOY_KEY:-$APP_ROOT/agent/github_deploy_ed25519}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[bootstrap] Installing base packages..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl openssh-server openssh-client ufw openssl git >/dev/null

echo "[bootstrap] Ensuring Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker info >/dev/null

echo "[bootstrap] Ensuring SSH..."
systemctl enable --now ssh

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

install -d -m 0700 "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 0600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

if [[ -n "$DEPLOY_PUBLIC_KEY" ]] && ! grep -Fqx "$DEPLOY_PUBLIC_KEY" "/home/$DEPLOY_USER/.ssh/authorized_keys"; then
  printf '%s\n' "$DEPLOY_PUBLIC_KEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

install -d -m 0755 "$APP_ROOT" "$APP_ROOT/infra" "$APP_ROOT/agent"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT"

# Dedicated read-only GitHub repository identity. The private key never enters Git.
if [[ ! -f "$GITHUB_KEY" ]]; then
  umask 077
  ssh-keygen -t ed25519 -N "" -C "chuma-vps-readonly" -f "$GITHUB_KEY" >/dev/null
fi
chmod 600 "$GITHUB_KEY"
chmod 644 "${GITHUB_KEY}.pub"

# Pin GitHub's SSH host key once so the updater does not trust arbitrary hosts.
GITHUB_KNOWN_HOSTS="$APP_ROOT/agent/github_known_hosts"
if [[ ! -s "$GITHUB_KNOWN_HOSTS" ]]; then
  umask 077
  ssh-keyscan -H github.com > "$GITHUB_KNOWN_HOSTS" 2>/dev/null
  test -s "$GITHUB_KNOWN_HOSTS"
  chmod 600 "$GITHUB_KNOWN_HOSTS"
fi

if [[ ! -f "$APP_ROOT/infra/.env" ]]; then
  umask 077
  POSTGRES_PASSWORD="$(openssl rand -hex 32)"
  CHUMA_ADMIN_TOKEN="$(openssl rand -hex 48)"
  cat > "$APP_ROOT/infra/.env" <<EOF
# Generated automatically.
CHUMA_DOMAIN=:80
ACME_EMAIL=
POSTGRES_DB=chuma
POSTGRES_USER=chuma
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
CHUMA_ADMIN_TOKEN=$CHUMA_ADMIN_TOKEN
CHUMA_SPEND_MODE=free
CHUMA_ALLOW_PAID_GENERATION=false
CHUMA_MONTHLY_SOFT_CAP_USD=0
CHUMA_MONTHLY_HARD_CAP_USD=0
BACKUP_RETENTION_DAYS=14
BACKUP_DIR=./backups
EOF
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT/infra/.env"
  chmod 600 "$APP_ROOT/infra/.env"
fi

echo "[bootstrap] Configuring firewall..."
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "[bootstrap] OK"
echo "[bootstrap] GitHub public key: ${GITHUB_KEY}.pub"
echo "[bootstrap] Add this PUBLIC key to the private repository Deploy Keys (read-only):"
cat "${GITHUB_KEY}.pub"
