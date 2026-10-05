#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
QUEUE="$APP_ROOT/agent/chuma-job-queue.sh"
FIREWALL="$APP_ROOT/agent/chuma-capability-firewall.sh"
INTEL="$APP_ROOT/agent/chuma-intelligence.sh"
TASKLANG="$APP_ROOT/agent/chuma-task-language.sh"
REGISTRY="$APP_ROOT/agent/chuma-operation-registry.sh"
LOCK="$ROOT/state/dispatcher.lock"
LOG="$ROOT/state/dispatcher.log"
INTERVAL="${CHUMA_DISPATCH_INTERVAL:-5}"
mkdir -p "$ROOT/state"; chmod 700 "$ROOT/state"; touch "$LOG"; chmod 600 "$LOG"
exec 9>"$LOCK"; flock -n 9 || exit 0
log(){ printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }
getv(){ sed -n "s/^$2=//p" "$1"; }
run_job(){
  local id="$1" f="$ROOT/state/jobs/$id.env" project task mode risk meta operation capability executor output rc
  [[ -f "$f" ]] || return 44
  project="$(getv "$f" project)"; task="$(getv "$f" task)"; mode="$(getv "$f" autonomy_mode)"; risk="$(getv "$f" risk_ceiling)"
  "$QUEUE" set-status "$id" DISPATCHED >/dev/null || return
  meta=$("$TASKLANG" parse "$project" "$task" 2>/dev/null) || {
    "$QUEUE" set-status "$id" BLOCKED "" unknown_operation >/dev/null || true
    "$INTEL" event "$project" job_blocked "job=$id reason=unknown_operation" >/dev/null || true
    return
  }
  operation="$(printf '%s\n' "$meta" | sed -n 's/^operation=//p')"
  capability="$(printf '%s\n' "$meta" | sed -n 's/^capability=//p')"
  [[ -n "$operation" && -n "$capability" ]] || { "$QUEUE" set-status "$id" BLOCKED "" invalid_operation_metadata >/dev/null || true; return; }
  "$REGISTRY" validate "$project" "$operation" >/dev/null 2>&1 || { "$QUEUE" set-status "$id" BLOCKED "" operation_not_registered >/dev/null || true; return; }
  [[ "$risk" == "$capability" || ( "$risk" == "WRITE" && "$capability" == "WRITE" ) || ( "$risk" == "READ" && "$capability" == "READ" ) ]] || {
    "$QUEUE" set-status "$id" BLOCKED "" risk_capability_mismatch >/dev/null || true
    return
  }
  "$FIREWALL" check "$mode" "$capability" >/dev/null 2>&1 || { "$QUEUE" set-status "$id" BLOCKED "" capability_denied >/dev/null || true; return; }
  if [[ -f "$ROOT/state/SAFE_MODE" ]]; then "$QUEUE" set-status "$id" BLOCKED "" safe_mode >/dev/null || true; return; fi
  "$QUEUE" set-status "$id" RUNNING >/dev/null || return
  "$INTEL" event "$project" operation_started "job=$id operation=$operation" >/dev/null || true
  executor="$APP_ROOT/agent/executors/${project}.sh"
  [[ -x "$executor" ]] || { "$QUEUE" set-status "$id" BLOCKED "" executor_not_installed >/dev/null || true; return; }
  set +e
  output=$(timeout 1800 "$executor" "$id" "$operation" "$task" 2>&1)
  rc=$?
  set -e
  "$QUEUE" set-status "$id" VERIFYING "$output" "" >/dev/null || true
  if (( rc != 0 )); then
    "$QUEUE" set-status "$id" FAILED "" "executor_exit=$rc" >/dev/null || true
    "$INTEL" event "$project" operation_failed "job=$id operation=$operation rc=$rc" >/dev/null || true
    if "$QUEUE" retry "$id" >/dev/null 2>&1; then "$INTEL" event "$project" job_retrying "job=$id operation=$operation" >/dev/null || true; fi
    return
  fi
  "$INTEL" checkpoint "$project" "job=$id operation=$operation" "verification_passed" >/dev/null || true
  "$QUEUE" set-status "$id" SUCCEEDED "$output" "" >/dev/null || true
  "$INTEL" event "$project" operation_completed "job=$id operation=$operation" >/dev/null || true
}
recover_stale(){
  local now f st updated epoch id
  now=$(date +%s)
  for f in "$ROOT/state/jobs"/JOB-*.env; do
    [[ -f "$f" ]] || continue
    st="$(getv "$f" status)"; id="$(getv "$f" job_id)"
    [[ "$st" == RUNNING || "$st" == VERIFYING || "$st" == DISPATCHED ]] || continue
    updated="$(getv "$f" updated_at)"; epoch=$(date -d "$updated" +%s 2>/dev/null || echo "$now")
    if (( now-epoch > 2100 )); then
      "$QUEUE" set-status "$id" FAILED "" stale_job_timeout >/dev/null || true
      if "$QUEUE" retry "$id" >/dev/null 2>&1; then "$INTEL" event "$(getv "$f" project)" job_recovered "job=$id action=retry" >/dev/null || true; else "$INTEL" event "$(getv "$f" project)" job_blocked "job=$id reason=stale_retry_limit" >/dev/null || true; fi
    fi
  done
}
while true; do
  recover_stale
  for f in "$ROOT/state/jobs"/JOB-*.env; do
    [[ -f "$f" ]] || continue
    st="$(getv "$f" status)"
    [[ "$st" == QUEUED || "$st" == RETRYING ]] || continue
    run_job "$(getv "$f" job_id)" || true
  done
  sleep "$INTERVAL"
done
