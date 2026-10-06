#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/opt/chuma"
PUBLIC_IP="${CHUMA_PUBLIC_IP:-161.104.32.15}"
REPO="https://github.com/texx013-boop/CHUMA-IP-FACTORY.git"
TMP="/tmp/mini-ip-finish-$(date +%s)"
BACKUP="${ROOT}.pre-final-$(date +%Y%m%d-%H%M%S)"
[[ "$EUID" -eq 0 ]] || { echo "Запустите от root."; exit 1; }
export DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0
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
echo "[5/8] Сборка и запуск..."
cd "$ROOT/infra"
docker compose up -d --build
docker compose ps
echo "[6/8] Локальная проверка..."
for i in $(seq 1 60); do
  curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS --max-time 10 http://127.0.0.1/health >/dev/null
curl -fsS --max-time 10 http://127.0.0.1/ready >/dev/null
echo "[7/8] Проверка браузерного контура..."
UI="$(curl -fsS --max-time 15 "http://$PUBLIC_IP/")"
grep -q "MINI IP" <<<"$UI"
grep -q "Персонаж" <<<"$UI"
grep -q "Создать контент" <<<"$UI"
grep -q "Карточка персонажа" <<<"$UI"
grep -q "Обучение и сигналы" <<<"$UI"
grep -q "Эволюция персонажа" <<<"$UI"
curl -fsS --max-time 15 "http://$PUBLIC_IP/health" >/dev/null
curl -fsS --max-time 15 "http://$PUBLIC_IP/ready" >/dev/null
echo "[8/8] Проверка после перезапуска..."
docker compose restart
sleep 5
curl -fsS --max-time 10 http://127.0.0.1/health >/dev/null
curl -fsS --max-time 10 http://127.0.0.1/ready >/dev/null
curl -fsS --max-time 10 "http://$PUBLIC_IP/health" >/dev/null
trap - EXIT
rm -rf "$TMP"
echo
echo "MINI IP FINAL READY"
echo "http://$PUBLIC_IP/"
echo "Предыдущая версия: $BACKUP"
