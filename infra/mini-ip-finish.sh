#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/chuma"
PUBLIC_IP="${CHUMA_PUBLIC_IP:-161.104.32.15}"
REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
TMP="/tmp/mini-ip-finish-$(date +%s)"
BACKUP="${ROOT}.pre-final-$(date +%Y%m%d-%H%M%S)"
STAGE="startup"

[[ "$EUID" -eq 0 ]] || { echo "Запустите от root."; exit 1; }

export DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0
command -v rsync >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y rsync; }
mkdir -p "$TMP"

rollback() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "Ошибка на этапе: $STAGE"
    echo "Автоматический откат новой версии..."
    rm -rf "$ROOT"
    if [[ -d "$BACKUP" ]]; then
      mv "$BACKUP" "$ROOT"
      if [[ -d "$ROOT/infra" ]]; then
        cd "$ROOT/infra"
        docker compose up -d --build || true
      fi
    fi
  fi
  rm -rf "$TMP"
  exit $rc
}
trap rollback EXIT

STAGE="получение исходников"
echo "[1/8] Получение исходников..."
git clone --depth 1 --single-branch "$REPO" "$TMP/repo"

STAGE="проверка исходников"
echo "[2/8] Проверка исходников..."
python3 -m compileall -q "$TMP/repo/chuma_ip_factory" "$TMP/repo/run.py"

STAGE="резервная копия"
echo "[3/8] Резервная копия..."
if [[ -d "$ROOT" ]]; then mv "$ROOT" "$BACKUP"; fi

STAGE="установка файлов"
echo "[4/8] Установка новой версии..."
mkdir -p "$ROOT"
cp -a "$TMP/repo/." "$ROOT/"
if [[ -f "$BACKUP/infra/.env" ]]; then
  cp "$BACKUP/infra/.env" "$ROOT/infra/.env"
  chmod 600 "$ROOT/infra/.env"
fi

STAGE="сборка Docker"
echo "[5/8] Сборка и запуск..."
cd "$ROOT/infra"
docker compose up -d --build
docker compose ps || true

STAGE="проверка приложения"
echo "[6/8] Проверка приложения..."
for i in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=3)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=5)"
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=5)"
docker compose exec -T proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

CADDY_HOST="$(docker compose exec -T proxy /bin/sh -c 'printf %s "$CHUMA_DOMAIN"' | tr -d '\r')"
[[ -n "$CADDY_HOST" ]]

STAGE="проверка Mini IP"
echo "[7/8] Проверка браузерного контура..."
UI="$(curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/)"
grep -q "MINI IP" <<<"$UI"
grep -q "Персонаж" <<<"$UI"
grep -q "Фото персонажа" <<<"$UI"
grep -q "Путь персонажа" <<<"$UI"
grep -q "Создать первый контент" <<<"$UI"

curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/health >/dev/null
curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/ready >/dev/null

# После успешной проверки самого продукта новая версия считается принятой.
# Ошибка host-level Agent/Dev Console больше не должна откатывать рабочий веб-продукт.
trap - EXIT
rm -rf "$TMP"

echo "[8/8] Проверка после перезапуска..."
cd "$ROOT/infra"
docker compose restart
for i in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=3)" >/dev/null 2>&1 &&      docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=3)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health', timeout=5)"
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/ready', timeout=5)"
curl -fsS --max-time 10 -H "Host: $CADDY_HOST" http://127.0.0.1/health >/dev/null
curl -fsS --max-time 10 -H "Host: $CADDY_HOST" http://127.0.0.1/ready >/dev/null

echo
echo "[FINAL] Mini IP успешно развёрнут."
echo "URL: http://$PUBLIC_IP/"
echo "Предыдущая версия сохранена: $BACKUP"

echo
echo "[FINAL] Установка Control/Dev Console..."
if chmod +x "$ROOT/infra/agent-install.sh" "$ROOT/infra/chuma-dev-api.py" 2>/dev/null && "$ROOT/infra/agent-install.sh"; then
  if PAIR_CODE="$(python3 "$ROOT/agent/chuma-control-api.py" pair 2>/dev/null)" && [[ -n "$PAIR_CODE" ]] && [[ ${#PAIR_CODE} -ge 20 ]]; then
    echo "Dev Console: http://$PUBLIC_IP/control/dev/"
    echo "Код первого сопряжения: $PAIR_CODE"
  else
    echo "Dev Console установлена, но код сопряжения не удалось получить автоматически."
  fi
else
  echo "Веб-продукт работает; host-level Control/Dev Console потребует отдельной донастройки."
fi

echo "MINI IP FINAL READY"
