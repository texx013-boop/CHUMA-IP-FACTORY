# GLOBAL FACTORY 2 — Continuation Point

Date: 2026-10-08
Current release: 0.1.0

Latest saved checkpoint: 774a9795486c94a8ec66d5bfd8bfaf37502a7875
Main branch: main
Current commit: 774a9795486c94a8ec66d5bfd8bfaf37502a7875

## Completed

- Added Global Factory 2 control plane on top of existing CHUMA execution core.
- Owner registration/login and bearer session.
- One-button START / PAUSE / EMERGENCY STOP.
- Autonomous job worker.
- Growth Fund balance.
- Organic / Boost / Aggressive growth modes.
- Autonomy levels 0–4.
- Dashboard: IP, content, publications, platforms, fund, events.
- Platform compliance is fail-closed.
- Unknown/unverified platforms default to YELLOW / OWNER_REVIEW.
- Social passwords are not accepted or stored.
- OAuth/API is the intended connection mechanism.
- Safe Mode after emergency stop.
- Factory 2 runtime integrated into run.py.
- Docker/Render/Docker Compose runtime configuration updated.
- Tests added in tests/test_factory2.py.
- README updated.

## Important boundary

This is the first working control-plane foundation, not the final production product.

External social publishing is intentionally NOT enabled automatically yet.

## Next execution blocks

1. Run the actual test suite/build and fix every failure.
2. Harden Owner authentication/session/security and persistent storage.
3. Implement configurable compliance registry and current-status review workflow.
4. Implement real OAuth/API adapters only for explicitly approved platforms.
5. Build Character → Content → Distribution → Metrics → Learning loop on the existing CHUMA core.
6. Implement real Growth Fund spending ledger, daily/monthly limits, approvals and audit.
7. Add Owner Attention Engine and actionable notifications.
8. Add IP Memory, Experiment Engine, IP Health and IP Portfolio Manager.
9. Add provider abstraction/fallback for AI/content providers.
10. Deploy to a Russian Linux cloud environment and perform real production smoke/regression/security tests.
11. Only after the safe production path works, expand toward Opportunity Engine, IP Network, Economics and Venture Builder.

## Operating rule

Continue in MAX AUTONOMOUS + FINISH mode. Do not return to architecture-only discussion. Implement, test, fix, retest, secure, deploy, verify and save.

Owner should ultimately need only: login → connect approved services → optional fund → START → periodic statistics/review.


## 2026-10-07 — Internal Growth Loop Hardening
- Fixed learning provenance: pending/placeholder signals are ignored by Factory 2 learning.
- Replaced the old zero-value `awaiting_distribution` learning signal with measured results from the existing local test distribution contour.
- Factory 2 now records the internal contour explicitly as `measurement.mode=test_fixture` when the built-in test provider is used.
- Growth experiment lifecycle now records `MEASURED` plus publication and measurement provenance.
- Mirrored measured views/engagement/follows into Factory 2 signals with explicit `source=test_fixture` or `external`; no test metric is presented as real audience data.
- Added regression coverage for measured growth learning and protection against placeholder metrics influencing decisions.
- Code commits: `328d5def7249f4b7f5e6da49f4f3f8ea61ba4901`, tests `f09f1a9864d8f0be3ebee61cb69d7fba0f854210`.
- External social publishing remains disabled/fail-closed; this block is an internal integration test contour only.


## 2026-10-07 — Compliance Core
- Added configurable `gf_compliance_rules` registry with platform/action/jurisdiction scope.
- Unknown or expired rules remain **YELLOW / OWNER_REVIEW** by default.
- GREEN is never inferred from API availability; automation must be explicitly allowed by a current rule.
- RED remains non-automatable.
- Added owner-controlled compliance update API and regression coverage.
- Social credentials/passwords remain unsupported; connection remains OAuth/API only.
- This registry is an operational control layer, not a legal guarantee; current jurisdiction-specific rules must be reviewed before enabling automation.
- Latest code/test commits: `ca3cda6e18241900e20cd4ded0ea22939b2a307a`, `303f7e9a03c21a78ffa22c484978b559b9387636`, `1d0c17ffb9c616e5d7c69eb206e0d518d24c88b4`.


## 2026-10-08 — External Distribution Boundary
- Added provider-agnostic `gf_distributions` records with explicit states, provenance and unique idempotency keys.
- External distribution is fail-closed: unknown/YELLOW/RED compliance blocks before adapter execution; GREEN still requires an OAuth/API connection reference.
- Platform connections now store only `account_id` and a credential-manager reference; raw social passwords are not accepted as connection data.
- Added guarded prepare/submit/measurement API endpoints.
- Default external adapter is a non-network stub: it records `SUBMITTED` and never publishes to a real platform.
- External measurements are stored with `source=external`, remain separate from `test_fixture`, and move an experiment through `AWAITING_MEASUREMENT → MEASURED` before learning.
- Added regression tests for YELLOW/RED blocking, GREEN+OAuth path, idempotency, password-free connection metadata, and measurement state transitions.
- Latest code/test commits: `6d856bde261ef5299065bc8486315816a607e938`, `9c517c0c41b24ec401f224bcdee5b51fd5a1afeb`, `2a747722400a58354ccbd5cdfb7607f0b96192e6`, `5bec4ac576ba3feb63d488710a26c337328e90ee`, `b1866d7c778f0824a44fb94696c2a0243fc6c5db`, `193ee23f05a326485873a78dc6071c2d6da0986b`.
- CI result for these new push commits has not been observed through the available GitHub workflow-run endpoint yet; therefore this block is saved but not claimed as CI-verified.


## 2026-10-08 — Final hardening of Distribution boundary
- Fixed the Python class-boundary regression introduced while adding the external adapter; Factory 2 methods are again owned by `Factory2`.
- A platform is now `READY` only when the compliance rule is GREEN + automation is explicitly allowed + both account ID and a credential-manager reference exist.
- Raw credential values are rejected; accepted references must use `secret-manager://`, `oauth://` or `vault://` schemes.
- Added regression coverage for raw credential rejection.
- Latest saved code/test commits: `e3e28a3e2806adeace5728240cc8dcd337605466`, `2ea42e3e36c0b6b56b2966237cf91af240582b5b`, `f093d686b288668cc137858af11940374cdd7d9d`.
- GitHub workflow status is not claimed because the available workflow-run endpoint does not expose push-triggered runs for these commits. The saved source is the final reviewed checkpoint for this block.


## 2026-10-08 — Provider Adapter Boundary Finalized
- Added an explicit provider adapter registry.
- Unregistered providers always fall back to the non-network safe adapter; no hidden provider selection or network publishing exists.
- The adapter contract is now the stable integration point for future official OAuth/API providers.
- Added regression coverage proving the fallback adapter cannot produce an external ID or real publication.
- Latest code/test commits: `ae87784209a2d32091472711cf308ee2723df58e`, `3bd21a1e597ef9924623a87380e9ecacf6741cad`.
- Real server deployment was not attempted because the connected remote device was unavailable and the execution environment has no outbound network access.
