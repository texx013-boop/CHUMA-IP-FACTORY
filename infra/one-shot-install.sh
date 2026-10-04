#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/chuma
ARCHIVE=${1:-}
[[ ${EUID} -eq 0 ]] || { echo "Run as root"; exit 1; }

if [[ -z "$ARCHIVE" ]]; then
  for f in /opt/CHUMA-IP-FACTORY*.zip /opt/CHUMA-IP-FACTORY*.tar.gz /root/CHUMA-IP-FACTORY*.zip /root/CHUMA-IP-FACTORY*.tar.gz; do
    [[ -f "$f" ]] && { ARCHIVE="$f"; break; }
  done
fi
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || { echo "Archive not found"; exit 2; }

apt-get update -qq
apt-get install -y -qq ca-certificates curl openssl unzip tar >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

STAMP=$(date +%Y%m%d-%H%M%S)
if [[ -d "$ROOT" ]]; then
  mv "$ROOT" "${ROOT}.previous-${STAMP}"
fi
mkdir -p "$ROOT"

case "$ARCHIVE" in
  *.zip) unzip -q "$ARCHIVE" -d /tmp/chuma-install ;;
  *.tar.gz) mkdir -p /tmp/chuma-install; tar -xzf "$ARCHIVE" -C /tmp/chuma-install ;;
  *) echo "Unsupported archive"; exit 3 ;;
esac

SRC=$(find /tmp/chuma-install -maxdepth 2 -type f -name Dockerfile -print -quit | xargs -r dirname)
[[ -n "$SRC" ]] || { echo "CHUMA source not found in archive"; exit 4; }
cp -a "$SRC"/. "$ROOT"/
rm -rf /tmp/chuma-install

cd "$ROOT"
bash infra/bootstrap.sh
cd "$ROOT/infra"
docker compose up -d --build

for i in {1..60}; do
  if curl -fsS http://127.0.0.1:8097/health >/dev/null 2>&1; then
    if [[ -x "$ROOT/infra/agent-install.sh" ]]; then
      "$ROOT/infra/agent-install.sh"
    fi
    echo "CHUMA READY"
    exit 0
  fi
  sleep 2
done

echo "CHUMA HEALTH CHECK FAILED"
docker compose logs --tail=80
exit 5
