#!/usr/bin/env bash
set -u

ROOT="/opt/chuma"
PUBLIC_IP="${CHUMA_PUBLIC_IP:-161.104.32.15}"
REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
TMP="/tmp/mini-ip-web-$(date +%s)"
BACKUP="/opt/chuma.previous-$(date +%Y%m%d-%H%M%S)"

if [ "$EUID" -ne 0 ]; then
  echo "ROOT REQUIRED"
  exit 1
fi

echo "MINI IP WEB DEPLOY START"
rm -rf "$TMP"
mkdir -p "$TMP"

echo "1/5 DOWNLOAD"
if ! git clone --depth 1 --single-branch "$REPO" "$TMP/repo"; then
  echo "DOWNLOAD FAILED"
  exit 1
fi

echo "2/5 SAVE CONFIG"
if [ -d "$ROOT" ]; then
  mv "$ROOT" "$BACKUP"
fi
mkdir -p "$ROOT"
cp -a "$TMP/repo/." "$ROOT/"

if [ -f "$BACKUP/infra/.env" ]; then
  cp "$BACKUP/infra/.env" "$ROOT/infra/.env"
  chmod 600 "$ROOT/infra/.env"
fi

echo "3/5 BUILD WEB PRODUCT"
cd "$ROOT/infra" || exit 1
if ! docker compose up -d --build; then
  echo "DOCKER FAILED"
  rm -rf "$ROOT"
  [ -d "$BACKUP" ] && mv "$BACKUP" "$ROOT"
  cd "$ROOT/infra" 2>/dev/null && docker compose up -d --build >/dev/null 2>&1 || true
  exit 1
fi

echo "4/5 WEB PRODUCT STARTED"
docker compose ps

echo "5/5 FINAL"
rm -rf "$TMP"
echo
echo "================================"
echo "MINI IP FINAL READY"
echo "http://$PUBLIC_IP/"
echo "================================"
echo
echo "WEB PRODUCT DEPLOYED"
echo "Backup: $BACKUP"
