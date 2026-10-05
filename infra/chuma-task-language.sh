#!/usr/bin/env bash
set -Eeuo pipefail
parse(){
  local project="${1:-}" task="${2:-}"
  [[ "$project" =~ ^(SHUMA_SPACE|FILM_COMBAIN|PERSONAL_AI_COMPANION)$ ]] || { echo "invalid_project" >&2; return 64; }
  [[ -n "$task" && "${#task}" -le 2000 && "$task" != *$'\n'* && "$task" != *$'\r'* ]] || { echo "invalid_task" >&2; return 64; }
  local text="${task,,}" operation=VERIFY risk=READ capability=READ
  if [[ "$text" =~ (останов|stop) ]]; then
    operation=STOP; risk=WRITE; capability=WRITE
  elif [[ "$text" =~ (продолж|возобнов|resume) ]]; then
    operation=RESUME; risk=WRITE; capability=WRITE
  elif [[ "$text" =~ (поставь[[:space:]]+задач|установи[[:space:]]+задач|set[[:space:]]*task) ]]; then
    operation=SET_TASK; risk=WRITE; capability=WRITE
  elif [[ "$text" =~ (status|статус) ]]; then
    operation=STATUS
  elif [[ "$text" =~ (проверь|провер|verify) ]]; then
    operation=VERIFY
  else
    echo "unknown_operation" >&2
    return 44
  fi
  printf 'mode=NORMAL\nrisk=%s\ncapability=%s\napproval=NO\nproject=%s\noperation=%s\ntask=%s\n' "$risk" "$capability" "$project" "$operation" "$task"
}
case "${1:-}" in
  parse) shift; [[ $# -eq 2 ]] || exit 64; parse "$1" "$2";;
  *) echo "usage: parse PROJECT TASK" >&2; exit 64;;
esac
