#!/usr/bin/env bash
set -Eeuo pipefail
valid_project(){ [[ "${1:-}" =~ ^(SHUMA_SPACE|FILM_COMBAIN|PERSONAL_AI_COMPANION)$ ]]; }
valid_operation(){ [[ "${1:-}" =~ ^(STATUS|VERIFY|RESUME|SET_TASK|STOP)$ ]]; }
meta(){
  local project="${1:-}" op="${2:-}"
  valid_project "$project" && valid_operation "$op" || { echo "unknown_operation" >&2; return 44; }
  local risk=READ capability=READ executor="executors/$project.sh" verification=agent_verify timeout=300 retry=2 approval=NO
  case "$op" in
    STATUS) risk=READ; capability=READ; verification=agent_verify; timeout=120; retry=1;;
    VERIFY) risk=READ; capability=READ; verification=agent_verify; timeout=180; retry=1;;
    RESUME) risk=WRITE; capability=WRITE; verification=workspace_and_agent_verify; timeout=300; retry=1;;
    SET_TASK) risk=WRITE; capability=WRITE; verification=task_persisted; timeout=120; retry=0;;
    STOP) risk=WRITE; capability=WRITE; verification=workspace_stopped; timeout=120; retry=0;;
  esac
  printf 'project=%s\noperation=%s\nrisk=%s\ncapability=%s\nexecutor=%s\nverification=%s\ntimeout=%s\nretry=%s\napproval=%s\n' "$project" "$op" "$risk" "$capability" "$executor" "$verification" "$timeout" "$retry" "$approval"
}
list(){ for p in SHUMA_SPACE FILM_COMBAIN PERSONAL_AI_COMPANION; do for o in STATUS VERIFY RESUME SET_TASK STOP; do meta "$p" "$o"; done; done; }
case "${1:-}" in
  meta) [[ $# -eq 3 ]] || exit 64; meta "$2" "$3";;
  validate) [[ $# -eq 3 ]] || exit 64; meta "$2" "$3" >/dev/null;;
  list) list;;
  *) echo "usage: meta|validate|list PROJECT OPERATION" >&2; exit 64;;
esac
