#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="\${APP_ROOT:-/opt/chuma}"
DEPLOY_USER="\${DEPLOY_USER:-chuma-deploy}"
DEPLOY_PUBLIC_KEY="\${DEPLOY_PUBLIC_KEY:-}"

if [[ "\$EUID" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssh-server ufw openssl

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker
systemctl enable --now ssh

if ! id "\$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "\$DEPLOY_USER"
fi

usermod -aG docker "\$DEPLOY_USER"

install -d -m 0700 "/home/\$DEPLOY_USER/.ssh"
touch "/home/\$DEPLOY_USER/.ssh/authorized_keys"
chmod 0600 "/home/\$DEPLOY_USER/.ssh/authorized_keys"
chown -R "\$DEPLOY_USER:\$DEPLOY_USER" "/home/\$DEPLOY_USER/.ssh"

if [[ -n "\$DEPLOY_PUBLIC_KEY" ]]; then
  if ! grep -Fqx "\$DEPLOY_PUBLIC_KEY" "/home/\$DEPLOY_USER/.ssh/authorized_keys"; then
    printf '%s\n' "\$DEPLOY_PUBLIC_KEY" >> "/home/\$DEPLOY_USER/.ssh/authorized_keys"
  fi
else
  echo "DEPLOY_PUBLIC_KEY is not set; deployment account was created without a CI/CD key."
fi

install -d -m 0755 "\$APP_ROOT" "\$APP_ROOT/infra"
chown "\$DEPLOY_USER:\$DEPLOY_USER" "\$APP_ROOT"

if [[ ! -f "\$APP_ROOT/infra/.env" ]]; then
  umask 077
  POSTGRES_PASSWORD="\$(openssl rand -hex 32)"
  CHUMA_ADMIN_TOKEN="\$(openssl rand -hex 48)"
  cat > "\$APP_ROOT/infra/.env" <<EOF
# Generated automatically. Replace CHUMA_DOMAIN later when a real domain is ready.
CHUMA_DOMAIN=:80
ACME_EMAIL=
POSTGRES_DB=chuma
POSTGRES_USER=chuma
POSTGRES_PASSWORD=\$POSTGRES_PASSWORD
CHUMA_ADMIN_TOKEN=\$CHUMA_ADMIN_TOKEN
CHUMA_SPEND_MODE=free
CHUMA_ALLOW_PAID_GENERATION=false
CHUMA_MONTHLY_SOFT_CAP_USD=0
CHUMA_MONTHLY_HARD_CAP_USD=0
BACKUP_RETENTION_DAYS=14
BACKUP_DIR=./backups
EOF
  chown "\$DEPLOY_USER:\$DEPLOY_USER" "\$APP_ROOT/infra/.env"
  chmod 600 "\$APP_ROOT/infra/.env"
fi

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "CHUMA bootstrap complete."
echo "Deployment user: \$DEPLOY_USER"
echo "Application root: \$APP_ROOT"
echo "No GitHub repository key is stored on this server."
echo "Next deployment is performed by the CI/CD pipeline."
