#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/opt/chuma"
PUBLIC_IP="${CHUMA_PUBLIC_IP:-161.104.32.15}"
REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
TMP="/tmp/mini-ip-finish-$(date +%s)"
BACKUP="${ROOT}.pre-final-$(date +%Y%m%d-%H%M%S)"
[[ "$EUID" -eq 0 ]] || { echo "Запустите от root."; exit 1; }
export DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0
command -v rsync >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y rsync; }
mkdir -p "$TMP"
echo "[1/8] Получение исходников..."
git clone --depth 1 --single-branch "$REPO" "$TMP/repo"
echo "[2/8] Проверка исходников..."
python3 -m compileall -q "$TMP/repo/chuma_ip_factory" "$TMP/repo/run.py"
echo "[3/8] Резервная копия..."
if [[ -d "$ROOT" ]]; then mv "$ROOT" "$BACKUP"; fi
rollback() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "Ошибка. Выполняю автоматический откат..."
    rm -rf "$ROOT"
    if [[ -d "$BACKUP" ]]; then
      mv "$BACKUP" "$ROOT"
      cd "$ROOT/infra"
      docker compose up -d --build || true
    fi
  fi
  rm -rf "$TMP"
  exit $rc
}
trap rollback EXIT
echo "[4/8] Установка новой версии..."
mkdir -p "$ROOT"
cp -a "$TMP/repo/." "$ROOT/"
if [[ -f "$BACKUP/infra/.env" ]]; then
  cp "$BACKUP/infra/.env" "$ROOT/infra/.env"
  chmod 600 "$ROOT/infra/.env"
fi
echo "[5/8] Установка Control/Dev Console и сборка..."
chmod +x "$ROOT/infra/agent-install.sh" "$ROOT/infra/chuma-dev-api.py" || true
"$ROOT/infra/agent-install.sh"
echo "[5/8] Сборка и запуск..."
cd "$ROOT/infra"
docker compose up -d --build
docker compose ps
echo "[6/8] Локальная проверка приложения..."
for i in $(seq 1 60); do
  docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=3)" >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=5)"
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=5)"
docker compose exec -T proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
CADDY_HOST="$(docker compose exec -T proxy /bin/sh -c 'printf %s "$CHUMA_DOMAIN"' | tr -d '')"
[[ -n "$CADDY_HOST" ]]
echo "[7/8] Проверка браузерного контура..."
# Проверяем Caddy с тем же Host, который реально настроен в production.
UI="$(curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/)"
grep -q "MINI IP" <<<"$UI"
grep -q "Персонаж" <<<"$UI"
grep -q "Фото персонажа" <<<"$UI"
grep -q "Путь персонажа" <<<"$UI"
grep -q "Создать первый контент" <<<"$UI"
DEV_CODE="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/control/dev/)"
[[ "$DEV_CODE" == "401" || "$DEV_CODE" == "200" ]]
curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/health >/dev/null
curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/ready >/dev/null
# Внешний probe только информативный: hairpin/NAT не должен откатывать здоровый сервер.
PUBLIC_HTTP="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "http://$PUBLIC_IP/" || true)"
echo "External HTTP probe: ${PUBLIC_HTTP:-failed}"
echo "[8/8] Проверка после перезапуска..."
docker compose restart
for i in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=3)" >/dev/null 2>&1 && \
     docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=3)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=5)"
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=5)"
curl -fsS --max-time 10 -H "Host: $CADDY_HOST" http://127.0.0.1/health >/dev/null
curl -fsS --max-time 10 -H "Host: $CADDY_HOST" http://127.0.0.1/ready >/dev/null
POST_RESTART_HTTP="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "http://$PUBLIC_IP/health" || true)"
echo "External HTTP after restart: ${POST_RESTART_HTTP:-failed}"
echo
echo "[FINAL] Генерация и проверка кода первого сопряжения..."
PAIR_CODE="$(python3 "$ROOT/agent/chuma-control-api.py" pair)"
[[ -n "$PAIR_CODE" ]]
[[ ${#PAIR_CODE} -ge 20 ]]
trap - EXIT
rm -rf "$TMP"
echo "MINI IP FINAL READY"
echo "http://$PUBLIC_IP/"
echo "Dev Console: http://$PUBLIC_IP/control/dev/"
echo "Код первого сопряжения Dev Console: $PAIR_CODE"
echo "Предыдущая версия: $BACKUP"
