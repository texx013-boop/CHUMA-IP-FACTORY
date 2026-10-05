#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REG="$ROOT/chuma-operation-registry.sh"
TASK="$ROOT/chuma-task-language.sh"
bash -n "$REG" "$TASK"
for p in SHUMA_SPACE FILM_COMBAIN PERSONAL_AI_COMPANION; do
  for o in STATUS VERIFY RESUME SET_TASK STOP; do
    bash "$REG" validate "$p" "$o"
    meta=$(bash "$REG" meta "$p" "$o")
    grep -q '^executor=executors/' <<<"$meta"
    grep -q '^verification=' <<<"$meta"
  done
done
check_parse(){
  local project="$1" expected="$2" text="$3" out
  out=$(bash "$TASK" parse "$project" "$text")
  grep -q "^project=$project$" <<<"$out"
  grep -q "^operation=$expected$" <<<"$out"
  grep -q '^risk=' <<<"$out"
  grep -q '^capability=' <<<"$out"
}
check_parse SHUMA_SPACE VERIFY "проверь SHUMA.SPACE"
check_parse SHUMA_SPACE RESUME "продолжи SHUMA.SPACE"
check_parse FILM_COMBAIN STOP "останови Film Combain"
check_parse PERSONAL_AI_COMPANION SET_TASK "поставь задачу Personal AI Companion: подготовить статус"
if bash "$TASK" parse SHUMA_SPACE "rm -rf /" >/dev/null 2>&1; then
  echo "unsafe task unexpectedly accepted" >&2
  exit 1
fi
echo "operation layer tests: OK"
