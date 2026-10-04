#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
DEPLOY_USER="${DEPLOY_USER:-chuma-deploy}"
DEPLOY_PUBLIC_KEY="${DEPLOY_PUBLIC_KEY:-}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssh-server ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable --now docker
systemctl enable --now ssh

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi

usermod -aG docker "$DEPLOY_USER"

install -d -m 0700 "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 0600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

if [[ -n "$DEPLOY_PUBLIC_KEY" ]]; then
  if ! grep -Fqx "$DEPLOY_PUBLIC_KEY" "/home/$DEPLOY_USER/.ssh/authorized_keys"; then
    printf '%s\n' "$DEPLOY_PUBLIC_KEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
  fi
else
  echo "DEPLOY_PUBLIC_KEY is not set; deployment account was created without a CI/CD key."
fi

install -d -m 0755 "$APP_ROOT"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT"

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "CHUMA bootstrap complete."
echo "Deployment user: $DEPLOY_USER"
echo "Application root: $APP_ROOT"
echo "No GitHub repository key is stored on this server."
echo "Next deployment is performed by the CI/CD pipeline."
