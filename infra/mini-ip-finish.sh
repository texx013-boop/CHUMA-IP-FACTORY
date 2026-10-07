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
echo "[1/7] Получение исходников..."
git clone --depth 1 --single-branch "$REPO" "$TMP/repo"

STAGE="проверка исходников"
echo "[2/7] Проверка исходников..."
python3 -m compileall -q "$TMP/repo/chuma_ip_factory" "$TMP/repo/run.py"

STAGE="резервная копия"
echo "[3/7] Резервная копия..."
if [[ -d "$ROOT" ]]; then mv "$ROOT" "$BACKUP"; fi

STAGE="установка файлов"
echo "[4/7] Установка новой версии..."
mkdir -p "$ROOT"
cp -a "$TMP/repo/." "$ROOT/"
if [[ -f "$BACKUP/infra/.env" ]]; then
  cp "$BACKUP/infra/.env" "$ROOT/infra/.env"
  chmod 600 "$ROOT/infra/.env"
fi

STAGE="сборка и запуск"
echo "[5/7] Сборка и запуск..."
cd "$ROOT/infra"
docker compose up -d --build
docker compose ps || true

STAGE="проверка Mini IP"
echo "[6/7] Проверка Mini IP..."
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

UI="$(curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/)"
grep -q "MINI IP" <<<"$UI"
grep -q "Персонаж" <<<"$UI"
grep -q "Фото персонажа" <<<"$UI"
grep -q "Путь персонажа" <<<"$UI"
grep -q "Создать первый контент" <<<"$UI"
curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/health >/dev/null
curl -fsS --max-time 15 -H "Host: $CADDY_HOST" http://127.0.0.1/ready >/dev/null

# Веб-продукт прошёл все обязательные проверки.
# С этого момента откат запрещён: Mini IP уже доказанно работает.
trap - EXIT
rm -rf "$TMP"
printf '%s\n' "READY" > "$ROOT/mini-ip-ready"
chmod 600 "$ROOT/mini-ip-ready"

echo "[7/7] Фиксация готового продукта..."
echo
echo "========================================"
echo "        MINI IP FINAL READY"
echo "========================================"
echo "URL: http://$PUBLIC_IP/"
echo "Предыдущая версия: $BACKUP"
echo "========================================"

# Дополнительные системные компоненты не могут отменить готовность веб-продукта.
echo
echo "[OPTIONAL] Control/Dev Console..."
if chmod +x "$ROOT/infra/agent-install.sh" "$ROOT/infra/chuma-dev-api.py" 2>/dev/null && "$ROOT/infra/agent-install.sh" >/tmp/mini-ip-agent-install.log 2>&1; then
  if PAIR_CODE="$(python3 "$ROOT/agent/chuma-control-api.py" pair 2>/dev/null)" && [[ -n "$PAIR_CODE" ]] && [[ ${#PAIR_CODE} -ge 20 ]]; then
    echo "Dev Console: http://$PUBLIC_IP/control/dev/"
    echo "Код первого сопряжения: $PAIR_CODE"
  else
    echo "Control/Dev Console установлена; код сопряжения будет создан при первом открытии."
  fi
else
  echo "Control/Dev Console отложена; веб-продукт уже готов."
fi

echo
echo "MINI IP FINAL READY"
