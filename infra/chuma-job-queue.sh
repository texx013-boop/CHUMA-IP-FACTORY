#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
JOBS="$ROOT/state/jobs"; EVENTS="$ROOT/state/events"; SEQ="$ROOT/state/job-seq"
mkdir -p "$JOBS" "$EVENTS"; chmod 700 "$JOBS" "$EVENTS"; touch "$SEQ"; chmod 600 "$SEQ"
valid(){ [[ "${1:-}" =~ ^[A-Za-z0-9._:-]+$ ]]; }
project(){ [[ "${1:-}" =~ ^[A-Za-z0-9._-]+$ ]]; }
emit(){ local id="$1" ev="$2" detail="${3:-}"; printf '%s|%s|%s|%s\n' "$(date -Is)" "$id" "$ev" "$detail" >> "$EVENTS/events.log"; chmod 600 "$EVENTS/events.log"; }
next_id(){ local n; n=$(cat "$SEQ" 2>/dev/null || echo 0); n=$((n+1)); printf '%s\n' "$n" > "$SEQ"; printf 'JOB-%08d\n' "$n"; }
create(){
  local p="$1" task="$2" mode="${3:-NORMAL}" session="${4:-mobile-control}" risk="${5:-WRITE}" id now
  project "$p" || { echo invalid_project >&2; return 64; }; [[ -n "$task" && "$task" != *$'\n'* && ${#task} -le 2000 ]] || { echo invalid_task >&2; return 64; }
  [[ "$mode" =~ ^(SAFE|NORMAL|AUTONOMOUS|MAX_AUTONOMOUS)$ ]] || { echo invalid_mode >&2; return 64; }
  [[ "$risk" =~ ^(READ|WRITE|BUILD|TEST|DEPLOY|NETWORK|DATABASE|DOCKER|SERVER)$ ]] || { echo invalid_risk >&2; return 64; }
  valid "$session" || { echo invalid_session >&2; return 64; }
  id=$(next_id); now=$(date -Is)
  umask 077
  cat > "$JOBS/$id.env" <<EOF
job_id=$id
project=$p
task=$task
status=QUEUED
task_status=queued
autonomy_mode=$mode
risk_ceiling=$risk
session=$session
created_at=$now
updated_at=$now
stage=QUEUED
result=
error=
correlation_id=$id
attempts=0
max_attempts=2
EOF
  chmod 600 "$JOBS/$id.env"; emit "$id" CREATED "project=$p mode=$mode risk=$risk"; printf '%s\n' "$id"
}
set_status(){
 local id="$1" st="$2" result="${3:-}" error="${4:-}" f="$JOBS/$1.env"
 [[ -f "$f" ]] || { echo job_not_found >&2; return 44; }
 [[ "$st" =~ ^(QUEUED|DISPATCHED|RUNNING|VERIFYING|SUCCEEDED|FAILED|RETRYING|BLOCKED|CANCELLED)$ ]] || { echo invalid_status >&2; return 64; }
 sed -i "s/^status=.*/status=$st/; s/^updated_at=.*/updated_at=$(date -Is)/; s/^stage=.*/stage=$st/; s/^result=.*/result=$result/; s/^error=.*/error=$error/" "$f"
 emit "$id" "STATUS_$st" "result=$result error=$error"; cat "$f"
}
get(){ [[ -f "$JOBS/$1.env" ]] || return 44; cat "$JOBS/$1.env"; }
list(){ for f in "$JOBS"/JOB-*.env; do [[ -f "$f" ]] || continue; . "$f"; printf '%s|%s|%s|%s|%s|%s\n' "$job_id" "$project" "$status" "$stage" "$autonomy_mode" "$updated_at"; done | sort -t'|' -k6,6r; }
retry(){
 local id="$1" f="$JOBS/$id.env" attempts max_attempts
 [[ -f "$f" ]] || { echo job_not_found >&2; return 44; }
 attempts=$(grep -E '^attempts=' "$f" | cut -d= -f2- || echo 0)
 max_attempts=$(grep -E '^max_attempts=' "$f" | cut -d= -f2- || echo 2)
 [[ "$attempts" =~ ^[0-9]+$ && "$max_attempts" =~ ^[0-9]+$ ]] || return 65
 if (( attempts >= max_attempts )); then
   set_status "$id" BLOCKED "" retry_limit_reached >/dev/null
   return 75
 fi
 attempts=$((attempts+1))
 sed -i "s/^attempts=.*/attempts=$attempts/; s/^updated_at=.*/updated_at=$(date -Is)/" "$f"
 set_status "$id" RETRYING "" "retry_attempt=$attempts" >/dev/null
}
events(){ [[ -f "$EVENTS/events.log" ]] && tail -n 200 "$EVENTS/events.log" || true; }
case "${1:-}" in
 create) [[ $# -ge 3 && $# -le 6 ]] || exit 64; create "$2" "$3" "${4:-NORMAL}" "${5:-mobile-control}" "${6:-WRITE}" ;;
 set-status) [[ $# -ge 3 && $# -le 5 ]] || exit 64; set_status "$2" "$3" "${4:-}" "${5:-}" ;;
 get) get "$2" ;;
 list) list ;;
 retry) [[ $# -eq 2 ]] || exit 64; retry "$2" ;;
 events) events ;;
 *) echo "usage: create|get|list|events|set-status" >&2; exit 64 ;;
esac
