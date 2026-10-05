#!/usr/bin/env bash
set -Eeuo pipefail
for p in docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md; do test -f "$p"; done
grep -q "Success means verified outcome" docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md
grep -q "does not silently reopen rejected choices" docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md
grep -q "No notification spam" docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md
grep -q "Never erase evidence" docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md
grep -q "immutable security boundaries" docs/CHUMA_GOAL_DECISION_RECOVERY_CORE_SPEC.md
echo "CHUMA Goal/Decision/Recovery contract: OK"
