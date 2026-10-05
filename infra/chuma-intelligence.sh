#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
CONTROL_ROOT="${CHUMA_CONTROL_ROOT:-$APP_ROOT/control}"
INTEL_ROOT="$CONTROL_ROOT/state/intelligence"
SAFE_MODE_FILE="$CONTROL_ROOT/state/SAFE_MODE"
AUTONOMY_FILE="$CONTROL_ROOT/state/AUTONOMY_MODE"
GOAL_ROOT="$INTEL_ROOT/goals"
DECISION_ROOT="$INTEL_ROOT/decisions"
EVENT_ROOT="$INTEL_ROOT/events"
RECOVERY_ROOT="$INTEL_ROOT/recovery"

umask 077
mkdir -p "$GOAL_ROOT" "$DECISION_ROOT" "$EVENT_ROOT" "$RECOVERY_ROOT"
chmod 700 "$INTEL_ROOT" "$GOAL_ROOT" "$DECISION_ROOT" "$EVENT_ROOT" "$RECOVERY_ROOT"

valid_project() { [[ "${1:-}" =~ ^[A-Za-z0-9._-]+$ ]]; }
valid_id() { [[ "${1:-}" =~ ^[A-Za-z0-9._:-]{8,128}$ ]]; }
safe_value() { [[ "${1:-}" != *$'\n'* && "${1:-}" != *$'\r'* ]]; }
now() { date -Is; }

file_for() {
  local root="$1" project="$2"
  valid_project "$project" || { echo "invalid project id" >&2; return 64; }
  printf '%s/%s.state' "$root" "$project"
}

autonomy_status() {
  if [[ -f "$AUTONOMY_FILE" ]]; then
    cat "$AUTONOMY_FILE"
  else
    printf 'autonomy_mode=L3\npolicy=MAX_AUTONOMOUS_FINISH\n'
  fi
}

autonomy_set() {
  local level="$1"
  [[ "$level" =~ ^L[0-4]$ ]] || { echo "invalid autonomy level" >&2; return 64; }
  [[ "$level" != "L4" ]] || { echo "L4 reserved" >&2; return 78; }
  printf 'autonomy_mode=%s\npolicy=MAX_AUTONOMOUS_FINISH\nupdated_at=%s\n' "$level" "$(now)" > "$AUTONOMY_FILE"
  chmod 600 "$AUTONOMY_FILE"
  printf 'autonomy.set=ok\n'
  cat "$AUTONOMY_FILE"
}

goal_status() {
  local p="$1" f
  f="$(file_for "$GOAL_ROOT" "$p")"
  if [[ ! -f "$f" ]]; then
    printf 'goal.status=none\nproject_id=%s\n' "$p"
    return 0
  fi
  cat "$f"
}

goal_set() {
  local p="$1" desired="$2" criteria="$3" risk="${4:-medium}" f
  valid_project "$p" || return 64
  [[ -n "$desired" && -n "$criteria" ]] && safe_value "$desired" && safe_value "$criteria" || {
    echo "goal requires non-empty single-line outcome and success criteria" >&2
    return 64
  }
  [[ "$risk" =~ ^(low|medium|high|critical)$ ]] || { echo "invalid risk ceiling" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"
  cat > "$f" <<EOF
project_id=$p
status=active
desired_outcome=$desired
success_criteria=$criteria
risk_ceiling=$risk
created_at=$(now)
updated_at=$(now)
last_verified_result=
blocker=
next_action=
EOF
  chmod 600 "$f"
  printf 'goal.set=ok\n'
  cat "$f"
}

goal_update() {
  local p="$1" status="$2" result="${3:-}" next="${4:-}" f tmp
  [[ "$status" =~ ^(active|blocked|completed|cancelled)$ ]] && safe_value "$result" && safe_value "$next" || {
    echo "invalid goal update values" >&2
    return 64
  }
  f="$(file_for "$GOAL_ROOT" "$p")"
  [[ -f "$f" ]] || { echo "goal not found" >&2; return 66; }
  tmp="$f.tmp.$$"
  awk -v s="$status" -v r="$result" -v n="$next" -v t="$(now)" '
    BEGIN { updated=0 }
    /^status=/ { print "status=" s; updated=1; next }
    /^last_verified_result=/ { print "last_verified_result=" r; updated=1; next }
    /^next_action=/ { print "next_action=" n; updated=1; next }
    /^updated_at=/ { print "updated_at=" t; updated=1; next }
    { print }
    END {
      if (!updated) exit 2
    }
  ' "$f" > "$tmp"
  chmod 600 "$tmp"
  mv -f -- "$tmp" "$f"
  printf 'goal.update=ok\n'
  cat "$f"
}

decision_add() {
  local p="$1" id="$2" decision="$3" rationale="$4" rejected="${5:-}" f
  valid_project "$p" && valid_id "$id" && safe_value "$decision" && safe_value "$rationale" && safe_value "$rejected" || {
    echo "invalid project, decision id, or decision text" >&2
    return 64
  }
  f="$DECISION_ROOT/${p}__${id}.state"
  [[ ! -e "$f" ]] || { echo "decision already exists" >&2; return 73; }
  cat > "$f" <<EOF
decision_id=$id
project_id=$p
status=active
decision=$decision
rationale=$rationale
alternatives_rejected=$rejected
created_at=$(now)
supersedes=
EOF
  chmod 600 "$f"
  printf 'decision.add=ok\n'
}

decision_list() {
  local p="$1" found=0 f
  valid_project "$p" || return 64
  for f in "$DECISION_ROOT/${p}"__*.state; do
    [[ -f "$f" ]] || continue
    found=1
    cat "$f"
    printf '\n'
  done
  (( found )) || printf 'decisions=empty\n'
}

event() {
  local p="$1" kind="$2" detail="$3" f
  valid_project "$p" || return 64
  safe_value "$kind" && safe_value "$detail" || { echo "event values must be single-line" >&2; return 64; }
  f="$EVENT_ROOT/${p}.log"
  printf '%s kind=%s detail=%s\n' "$(now)" "$kind" "$detail" >> "$f"
  chmod 600 "$f"
  printf 'event.recorded=ok\n'
}

events() {
  local p="$1" f
  f="$EVENT_ROOT/${p}.log"
  valid_project "$p" || return 64
  [[ -f "$f" ]] && cat "$f" || printf 'events=empty\n'
}

checkpoint() {
  local p="$1" stage="$2" result="$3" f="$RECOVERY_ROOT/${p}.checkpoint"
  valid_project "$p" && safe_value "$stage" && safe_value "$result" || {
    echo "invalid checkpoint values" >&2
    return 64
  }
  cat > "$f" <<EOF
project_id=$p
stage=$stage
verified_result=$result
created_at=$(now)
EOF
  chmod 600 "$f"
  event "$p" recovery_checkpoint "$stage" >/dev/null
  printf 'recovery.checkpoint=ok\n'
}

recovery_status() {
  local p="$1" f
  f="$RECOVERY_ROOT/${p}.checkpoint"
  valid_project "$p" || return 64
  [[ -f "$f" ]] && cat "$f" || printf 'recovery.checkpoint=none\n'
}

context() {
  local p="$1"
  valid_project "$p" || return 64
  printf 'CHUMA CONTEXT\nproject_id=%s\n' "$p"
  autonomy_status
  if [[ -f "$SAFE_MODE_FILE" ]]; then printf 'safe_mode=on\n'; else printf 'safe_mode=off\n'; fi
  goal_status "$p"
  recovery_status "$p"
  printf '%s\n' '--- decisions ---'
  decision_list "$p"
  printf '%s\n' '--- events ---'
  events "$p" | tail -20
}

watch() {
  local p="$1" g w f
  g="$GOAL_ROOT/${p}.state"
  w="$CONTROL_ROOT/state/workspaces/${p}.state"
  f="$EVENT_ROOT/${p}.log"
  valid_project "$p" || return 64
  local signaled=0
  if [[ -f "$g" ]]; then
    if grep -q '^status=blocked$' "$g"; then printf 'signal=goal_blocked\n'; signaled=1; fi
    if grep -q '^status=completed$' "$g"; then printf 'signal=goal_completed\n'; signaled=1; fi
  fi
  if [[ -f "$w" ]] && grep -q '^task_status=stopped$' "$w"; then
    printf 'signal=workspace_stopped\n'
    signaled=1
  fi
  if [[ -f "$f" ]]; then
    printf 'event_count=%s\n' "$(wc -l < "$f" | tr -d ' ')"
  fi
  (( signaled )) || printf 'signals=none\n'
}

usage() {
  cat <<'EOF'
CHUMA INTELLIGENCE
  goal set <project> <outcome> <success_criteria> [risk]
  goal status <project>
  goal update <project> <active|blocked|completed|cancelled> [result] [next_action]
  decision add <project> <decision_id> <decision> <rationale> [rejected]
  decision list <project>
  event <project> <kind> <detail>
  events <project>
  checkpoint <project> <stage> <verified_result>
  recovery status <project>
  context <project>
  autonomy status
  autonomy set <L0|L1|L2|L3>
  watch <project>
EOF
}

case "${1:-}" in
  autonomy)
    case "${2:-}" in
      status) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; autonomy_status ;;
      set) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; autonomy_set "$3" ;;
      *) usage >&2; exit 64 ;;
    esac ;;
  goal)
    case "${2:-}" in
      set) [[ $# -ge 5 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_set "$3" "$4" "$5" "${6:-medium}" ;;
      status) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; goal_status "$3" ;;
      update) [[ $# -ge 4 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_update "$3" "$4" "${5:-}" "${6:-}" ;;
      *) usage >&2; exit 64 ;;
    esac ;;
  decision)
    case "${2:-}" in
      add) [[ $# -ge 6 && $# -le 7 ]] || { usage >&2; exit 64; }; decision_add "$3" "$4" "$5" "$6" "${7:-}" ;;
      list) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; decision_list "$3" ;;
      *) usage >&2; exit 64 ;;
    esac ;;
  event) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; event "$2" "$3" "$4" ;;
  events) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; events "$2" ;;
  checkpoint) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; checkpoint "$2" "$3" "$4" ;;
  recovery) [[ "${2:-}" == status && $# -eq 3 ]] || { usage >&2; exit 64; }; recovery_status "$3" ;;
  context) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; context "$2" ;;
  watch) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; watch "$2" ;;
  *) usage >&2; exit 64 ;;
esac
