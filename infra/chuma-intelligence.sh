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

mkdir -p "$GOAL_ROOT" "$DECISION_ROOT" "$EVENT_ROOT" "$RECOVERY_ROOT"
chmod 700 "$INTEL_ROOT" "$GOAL_ROOT" "$DECISION_ROOT" "$EVENT_ROOT" "$RECOVERY_ROOT"

valid_project(){ [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]]; }
valid_id(){ [[ "$1" =~ ^[A-Za-z0-9._:-]{8,128}$ ]]; }
safe_value(){ [[ "$1" != *
file_for(){ local root="$1" project="$2"; valid_project "$project" || { echo "invalid project id" >&2; return 64; }; printf '%s/%s.state' "$root" "$project"; }
now(){ date -Is; }


autonomy_status(){
  if [[ -f "$AUTONOMY_FILE" ]]; then cat "$AUTONOMY_FILE"; else printf 'autonomy_mode=L3\npolicy=MAX_AUTONOMOUS_FINISH\n'; fi
}
autonomy_set(){
  local level="$1"
  [[ "$level" =~ ^L[0-4]$ ]] || { echo "invalid autonomy level" >&2; return 64; }
  [[ "$level" != "L4" ]] || { echo "L4 reserved" >&2; return 78; }
  umask 077
  printf 'autonomy_mode=%s\npolicy=MAX_AUTONOMOUS_FINISH\nupdated_at=%s\n' "$level" "$(now)" > "$AUTONOMY_FILE"
  chmod 600 "$AUTONOMY_FILE"
  printf 'autonomy.set=ok\n'; cat "$AUTONOMY_FILE"
}

goal_status(){
  local p="$1" f; f="$(file_for "$GOAL_ROOT" "$p")"
  if [[ ! -f "$f" ]]; then
    printf 'goal.status=none\nproject_id=%s\n' "$p"; return 0
  fi
  cat "$f"
}
goal_set(){
  local p="$1" desired="$2" criteria="$3" risk="${4:-medium}" f
  valid_project "$p" || return 64
  [[ -n "$desired" && -n "$criteria" ]] && safe_value "$desired" && safe_value "$criteria" || { echo "goal requires non-empty single-line outcome and success criteria" >&2; return 64; }
  [[ "$risk" =~ ^(low|medium|high|critical)$ ]] || { echo "invalid risk ceiling" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; umask 077
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
  printf 'goal.set=ok\n'; cat "$f"
}
goal_update(){
  local p="$1" status="$2" result="${3:-}" next="${4:-}" f
  [[ "$status" =~ ^(active|blocked|completed|cancelled)$ ]] && safe_value "$result" && safe_value "$next" || { echo "invalid goal update values" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; [[ -f "$f" ]] || { echo "goal not found" >&2; return 66; }
  awk -v s="$status" -v r="$result" -v n="$next" -v t="$(now)" '{sub(/^status=.*/, "status=" s); sub(/^last_verified_result=.*/, "last_verified_result=" r); sub(/^next_action=.*/, "next_action=" n); sub(/^updated_at=.*/, "updated_at=" t); print}' "$f" > "$f.tmp" && chmod 600 "$f.tmp" && mv -f -- "$f.tmp" "$f"
  printf 'goal.update=ok\n'; cat "$f"
}

decision_add(){
  local p="$1" id="$2" decision="$3" rationale="$4" rejected="${5:-}" f
  valid_project "$p" && valid_id "$id" && safe_value "$decision" && safe_value "$rationale" && safe_value "$rejected" || { echo "invalid project, decision id, or decision text" >&2; return 64; }
  f="$DECISION_ROOT/${p}__${id}.state"; [[ ! -e "$f" ]] || { echo "decision already exists" >&2; return 73; }
  umask 077
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
  chmod 600 "$f"; printf 'decision.add=ok\n'
}
decision_list(){
  local p="$1" found=0 f
  valid_project "$p" || return 64
  for f in "$DECISION_ROOT/${p}"__*.state; do
    [[ -f "$f" ]] || continue; found=1; cat "$f"; printf '\n'
  done
  ((found)) || printf 'decisions=empty\n'
}

event(){
  local p="$1" kind="$2" detail="$3" f
  valid_project "$p" || return 64
  f="$EVENT_ROOT/${p}.log"; umask 077
  printf '%s kind=%s detail=%s\n' "$(now)" "$kind" "$detail" >> "$f"; chmod 600 "$f"
  printf 'event.recorded=ok\n'
}
events(){ local p="$1" f="$EVENT_ROOT/${p}.log"; valid_project "$p" || return 64; [[ -f "$f" ]] && cat "$f" || printf 'events=empty\n'; }

checkpoint(){
  local p="$1" stage="$2" result="$3" f="$RECOVERY_ROOT/${p}.checkpoint"
  valid_project "$p" && safe_value "$stage" && safe_value "$result" || { echo "invalid checkpoint values" >&2; return 64; }; umask 077
  cat > "$f" <<EOF
project_id=$p
stage=$stage
verified_result=$result
created_at=$(now)
EOF
  chmod 600 "$f"; event "$p" recovery_checkpoint "$stage"; printf 'recovery.checkpoint=ok\n'
}
recovery_status(){
  local p="$1" f="$RECOVERY_ROOT/${p}.checkpoint"; valid_project "$p" || return 64
  [[ -f "$f" ]] && cat "$f" || printf 'recovery.checkpoint=none\n'
}

context(){
  local p="$1"; valid_project "$p" || return 64
  printf 'CHUMA CONTEXT\nproject_id=%s\n' "$p"
  autonomy_status
  if [[ -f "$SAFE_MODE_FILE" ]]; then printf 'safe_mode=on\n'; else printf 'safe_mode=off\n'; fi
  goal_status "$p"
  recovery_status "$p"
  printf '--- decisions ---\n'; decision_list "$p"
  printf '--- events ---\n'; events "$p" | tail -20
}

watch(){
  local p="$1" g="$GOAL_ROOT/$p.state" w="$CONTROL_ROOT/state/workspaces/$p.state" f="$EVENT_ROOT/${p}.log"
  valid_project "$p" || return 64
  if [[ -f "$g" ]]; then
    grep -q '^status=blocked$' "$g" && printf 'signal=goal_blocked\n'
    grep -q '^status=completed$' "$g" && printf 'signal=goal_completed\n'
  fi
  if [[ -f "$w" ]] && grep -q '^task_status=stopped$' "$w"; then printf 'signal=workspace_stopped\n'; fi
  if [[ ! -f "$g" && ! -f "$w" ]]; then printf 'signals=none\n'; return 0; fi
  [[ -f "$f" ]] && printf 'event_count=%s\n' "$(wc -l < "$f" | tr -d ' ')"
}

usage(){ cat <<'EOF'
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
  autonomy status\n  autonomy set <L0|L1|L2|L3>\n  watch <project>
EOF
}
case "${1:-}" in
 autonomy)
   case "${2:-}" in
     status) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; autonomy_status ;;
     set) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; autonomy_set "$3" ;;
     *) usage >&2; exit 64;;
   esac ;;
 goal)
   case "${2:-}" in
     set) [[ $# -ge 5 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_set "$3" "$4" "$5" "${6:-medium}" ;;
     status) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; goal_status "$3" ;;
     update) [[ $# -ge 4 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_update "$3" "$4" "${5:-}" "${6:-}" ;;
     *) usage >&2; exit 64;;
   esac ;;
 decision)
   case "${2:-}" in
     add) [[ $# -ge 6 && $# -le 7 ]] || { usage >&2; exit 64; }; decision_add "$3" "$4" "$5" "$6" "${7:-}" ;;
     list) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; decision_list "$3" ;;
     *) usage >&2; exit 64;;
   esac ;;
 event) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; event "$2" "$3" "$4" ;;
 events) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; events "$2" ;;
 checkpoint) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; checkpoint "$2" "$3" "$4" ;;
 recovery) [[ "${2:-}" == status && $# -eq 3 ]] || { usage >&2; exit 64; }; recovery_status "$3" ;;
 context) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; context "$2" ;;
 watch) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; watch "$2" ;;
 *) usage >&2; exit 64;;
esac
\n'* && "$1" != *
file_for(){ local root="$1" project="$2"; valid_project "$project" || { echo "invalid project id" >&2; return 64; }; printf '%s/%s.state' "$root" "$project"; }
now(){ date -Is; }

goal_status(){
  local p="$1" f; f="$(file_for "$GOAL_ROOT" "$p")"
  if [[ ! -f "$f" ]]; then
    printf 'goal.status=none\nproject_id=%s\n' "$p"; return 0
  fi
  cat "$f"
}
goal_set(){
  local p="$1" desired="$2" criteria="$3" risk="${4:-medium}" f
  valid_project "$p" || return 64
  [[ -n "$desired" && -n "$criteria" ]] || { echo "goal requires desired outcome and success criteria" >&2; return 64; }
  [[ "$risk" =~ ^(low|medium|high|critical)$ ]] || { echo "invalid risk ceiling" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; umask 077
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
  printf 'goal.set=ok\n'; cat "$f"
}
goal_update(){
  local p="$1" status="$2" result="${3:-}" next="${4:-}" f
  [[ "$status" =~ ^(active|blocked|completed|cancelled)$ ]] || { echo "invalid goal status" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; [[ -f "$f" ]] || { echo "goal not found" >&2; return 66; }
  sed -i "s/^status=.*/status=$status/; s/^last_verified_result=.*/last_verified_result=$result/; s/^next_action=.*/next_action=$next/; s/^updated_at=.*/updated_at=$(now)/" "$f"
  printf 'goal.update=ok\n'; cat "$f"
}

decision_add(){
  local p="$1" id="$2" decision="$3" rationale="$4" rejected="${5:-}" f
  valid_project "$p" && valid_id "$id" || { echo "invalid project or decision id" >&2; return 64; }
  f="$DECISION_ROOT/${p}__${id}.state"; [[ ! -e "$f" ]] || { echo "decision already exists" >&2; return 73; }
  umask 077
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
  chmod 600 "$f"; printf 'decision.add=ok\n'
}
decision_list(){
  local p="$1" found=0 f
  valid_project "$p" || return 64
  for f in "$DECISION_ROOT/${p}"__*.state; do
    [[ -f "$f" ]] || continue; found=1; cat "$f"; printf '\n'
  done
  ((found)) || printf 'decisions=empty\n'
}

event(){
  local p="$1" kind="$2" detail="$3" f
  valid_project "$p" || return 64
  f="$EVENT_ROOT/${p}.log"; umask 077
  printf '%s kind=%s detail=%s\n' "$(now)" "$kind" "$detail" >> "$f"; chmod 600 "$f"
  printf 'event.recorded=ok\n'
}
events(){ local p="$1" f="$EVENT_ROOT/${p}.log"; valid_project "$p" || return 64; [[ -f "$f" ]] && cat "$f" || printf 'events=empty\n'; }

checkpoint(){
  local p="$1" stage="$2" result="$3" f="$RECOVERY_ROOT/${p}.checkpoint"
  valid_project "$p" || return 64; umask 077
  cat > "$f" <<EOF
project_id=$p
stage=$stage
verified_result=$result
created_at=$(now)
EOF
  chmod 600 "$f"; event "$p" recovery_checkpoint "$stage"; printf 'recovery.checkpoint=ok\n'
}
recovery_status(){
  local p="$1" f="$RECOVERY_ROOT/${p}.checkpoint"; valid_project "$p" || return 64
  [[ -f "$f" ]] && cat "$f" || printf 'recovery.checkpoint=none\n'
}

context(){
  local p="$1"; valid_project "$p" || return 64
  printf 'CHUMA CONTEXT\nproject_id=%s\n' "$p"
  goal_status "$p"
  recovery_status "$p"
  printf '--- decisions ---\n'; decision_list "$p"
  printf '--- events ---\n'; events "$p" | tail -20
}

watch(){
  local p="$1" g="$GOAL_ROOT/$p.state" w="$CONTROL_ROOT/state/workspaces/$p.state" f="$EVENT_ROOT/${p}.log"
  valid_project "$p" || return 64
  if [[ -f "$g" ]]; then
    grep -q '^status=blocked$' "$g" && printf 'signal=goal_blocked\n'
    grep -q '^status=completed$' "$g" && printf 'signal=goal_completed\n'
  fi
  if [[ -f "$w" ]] && grep -q '^task_status=stopped$' "$w"; then printf 'signal=workspace_stopped\n'; fi
  if [[ ! -f "$g" && ! -f "$w" ]]; then printf 'signals=none\n'; return 0; fi
  [[ -f "$f" ]] && printf 'event_count=%s\n' "$(wc -l < "$f" | tr -d ' ')"
}

usage(){ cat <<'EOF'
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
  watch <project>
EOF
}
case "${1:-}" in
 goal)
   case "${2:-}" in
     set) [[ $# -ge 5 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_set "$3" "$4" "$5" "${6:-medium}" ;;
     status) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; goal_status "$3" ;;
     update) [[ $# -ge 4 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_update "$3" "$4" "${5:-}" "${6:-}" ;;
     *) usage >&2; exit 64;;
   esac ;;
 decision)
   case "${2:-}" in
     add) [[ $# -ge 6 && $# -le 7 ]] || { usage >&2; exit 64; }; decision_add "$3" "$4" "$5" "$6" "${7:-}" ;;
     list) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; decision_list "$3" ;;
     *) usage >&2; exit 64;;
   esac ;;
 event) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; event "$2" "$3" "$4" ;;
 events) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; events "$2" ;;
 checkpoint) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; checkpoint "$2" "$3" "$4" ;;
 recovery) [[ "${2:-}" == status && $# -eq 3 ]] || { usage >&2; exit 64; }; recovery_status "$3" ;;
 context) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; context "$2" ;;
 watch) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; watch "$2" ;;
 *) usage >&2; exit 64;;
esac
\r'* ]]; }
file_for(){ local root="$1" project="$2"; valid_project "$project" || { echo "invalid project id" >&2; return 64; }; printf '%s/%s.state' "$root" "$project"; }
now(){ date -Is; }

goal_status(){
  local p="$1" f; f="$(file_for "$GOAL_ROOT" "$p")"
  if [[ ! -f "$f" ]]; then
    printf 'goal.status=none\nproject_id=%s\n' "$p"; return 0
  fi
  cat "$f"
}
goal_set(){
  local p="$1" desired="$2" criteria="$3" risk="${4:-medium}" f
  valid_project "$p" || return 64
  [[ -n "$desired" && -n "$criteria" ]] || { echo "goal requires desired outcome and success criteria" >&2; return 64; }
  [[ "$risk" =~ ^(low|medium|high|critical)$ ]] || { echo "invalid risk ceiling" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; umask 077
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
  printf 'goal.set=ok\n'; cat "$f"
}
goal_update(){
  local p="$1" status="$2" result="${3:-}" next="${4:-}" f
  [[ "$status" =~ ^(active|blocked|completed|cancelled)$ ]] || { echo "invalid goal status" >&2; return 64; }
  f="$(file_for "$GOAL_ROOT" "$p")"; [[ -f "$f" ]] || { echo "goal not found" >&2; return 66; }
  sed -i "s/^status=.*/status=$status/; s/^last_verified_result=.*/last_verified_result=$result/; s/^next_action=.*/next_action=$next/; s/^updated_at=.*/updated_at=$(now)/" "$f"
  printf 'goal.update=ok\n'; cat "$f"
}

decision_add(){
  local p="$1" id="$2" decision="$3" rationale="$4" rejected="${5:-}" f
  valid_project "$p" && valid_id "$id" || { echo "invalid project or decision id" >&2; return 64; }
  f="$DECISION_ROOT/${p}__${id}.state"; [[ ! -e "$f" ]] || { echo "decision already exists" >&2; return 73; }
  umask 077
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
  chmod 600 "$f"; printf 'decision.add=ok\n'
}
decision_list(){
  local p="$1" found=0 f
  valid_project "$p" || return 64
  for f in "$DECISION_ROOT/${p}"__*.state; do
    [[ -f "$f" ]] || continue; found=1; cat "$f"; printf '\n'
  done
  ((found)) || printf 'decisions=empty\n'
}

event(){
  local p="$1" kind="$2" detail="$3" f
  valid_project "$p" || return 64
  f="$EVENT_ROOT/${p}.log"; umask 077
  printf '%s kind=%s detail=%s\n' "$(now)" "$kind" "$detail" >> "$f"; chmod 600 "$f"
  printf 'event.recorded=ok\n'
}
events(){ local p="$1" f="$EVENT_ROOT/${p}.log"; valid_project "$p" || return 64; [[ -f "$f" ]] && cat "$f" || printf 'events=empty\n'; }

checkpoint(){
  local p="$1" stage="$2" result="$3" f="$RECOVERY_ROOT/${p}.checkpoint"
  valid_project "$p" || return 64; umask 077
  cat > "$f" <<EOF
project_id=$p
stage=$stage
verified_result=$result
created_at=$(now)
EOF
  chmod 600 "$f"; event "$p" recovery_checkpoint "$stage"; printf 'recovery.checkpoint=ok\n'
}
recovery_status(){
  local p="$1" f="$RECOVERY_ROOT/${p}.checkpoint"; valid_project "$p" || return 64
  [[ -f "$f" ]] && cat "$f" || printf 'recovery.checkpoint=none\n'
}

context(){
  local p="$1"; valid_project "$p" || return 64
  printf 'CHUMA CONTEXT\nproject_id=%s\n' "$p"
  goal_status "$p"
  recovery_status "$p"
  printf '--- decisions ---\n'; decision_list "$p"
  printf '--- events ---\n'; events "$p" | tail -20
}

watch(){
  local p="$1" g="$GOAL_ROOT/$p.state" w="$CONTROL_ROOT/state/workspaces/$p.state" f="$EVENT_ROOT/${p}.log"
  valid_project "$p" || return 64
  if [[ -f "$g" ]]; then
    grep -q '^status=blocked$' "$g" && printf 'signal=goal_blocked\n'
    grep -q '^status=completed$' "$g" && printf 'signal=goal_completed\n'
  fi
  if [[ -f "$w" ]] && grep -q '^task_status=stopped$' "$w"; then printf 'signal=workspace_stopped\n'; fi
  if [[ ! -f "$g" && ! -f "$w" ]]; then printf 'signals=none\n'; return 0; fi
  [[ -f "$f" ]] && printf 'event_count=%s\n' "$(wc -l < "$f" | tr -d ' ')"
}

usage(){ cat <<'EOF'
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
  watch <project>
EOF
}
case "${1:-}" in
 goal)
   case "${2:-}" in
     set) [[ $# -ge 5 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_set "$3" "$4" "$5" "${6:-medium}" ;;
     status) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; goal_status "$3" ;;
     update) [[ $# -ge 4 && $# -le 6 ]] || { usage >&2; exit 64; }; goal_update "$3" "$4" "${5:-}" "${6:-}" ;;
     *) usage >&2; exit 64;;
   esac ;;
 decision)
   case "${2:-}" in
     add) [[ $# -ge 6 && $# -le 7 ]] || { usage >&2; exit 64; }; decision_add "$3" "$4" "$5" "$6" "${7:-}" ;;
     list) [[ $# -eq 3 ]] || { usage >&2; exit 64; }; decision_list "$3" ;;
     *) usage >&2; exit 64;;
   esac ;;
 event) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; event "$2" "$3" "$4" ;;
 events) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; events "$2" ;;
 checkpoint) [[ $# -eq 4 ]] || { usage >&2; exit 64; }; checkpoint "$2" "$3" "$4" ;;
 recovery) [[ "${2:-}" == status && $# -eq 3 ]] || { usage >&2; exit 64; }; recovery_status "$3" ;;
 context) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; context "$2" ;;
 watch) [[ $# -eq 2 ]] || { usage >&2; exit 64; }; watch "$2" ;;
 *) usage >&2; exit 64;;
esac
