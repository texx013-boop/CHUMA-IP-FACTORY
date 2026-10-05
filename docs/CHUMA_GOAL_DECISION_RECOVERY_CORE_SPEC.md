# CHUMA Goal, Decision, Proactive & Recovery Core

## Goal Engine
Natural-language intent is converted into a durable goal:
goal_id, project_id, desired_outcome, constraints, success_criteria, risk_ceiling, owner_policy, created_at, updated_at.
A goal may contain ordered tasks and may resume after interruption.
Success means verified outcome, not merely completed commands.

## Decision Memory
Store durable project decisions with:
decision_id, project_id, decision, rationale, alternatives_rejected, owner_scope, created_at, supersedes, status.
Before proposing a major architectural choice, CHUMA checks active decisions and does not silently reopen rejected choices.
A decision can be explicitly superseded.

## Proactive Watcher
Observe authoritative signals: CI, deployment state, workspace leases, health, backups, security alerts, blocked jobs.
Notify only when a signal changes state, requires owner action, creates material risk, or completes a meaningful goal.
No notification spam.

## Recovery Brain
On failure:
1. classify failure;
2. preserve evidence;
3. identify last verified good state;
4. select the safest reversible recovery;
5. execute only within policy/risk ceiling;
6. verify;
7. record outcome and rollback point;
8. resume the goal if safe.
Never erase evidence before recovery is verified.

## Goal-aware interaction
“Продолжай” means resume the highest-priority active goal for the current project/session.
“Где мы?” returns goal, verified progress, blocker, next action.
“Доведи до результата” permits L3 autonomous execution within the owner's risk ceiling.
“Стоп” immediately stops the active mutating task where supported.
“Безопасно” lowers the risk ceiling rather than disabling execution.

## Owner control
Goal and recovery policies cannot override immutable security boundaries.
Critical destructive actions remain step-up/owner controlled.
Self-learning can optimize routing and recovery patterns but cannot weaken security limits.
