# GLOBAL FACTORY 2 — Continuation Point

Date: 2026-10-08
Current release: 0.1.0

Latest saved checkpoint: 6e98e0ffb302cd0ec87675a903af3b24f50fb867
Main branch: main
Current commit: fe6be8ac81257262454f6e8d83c9e2eef9c28149

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


## 2026-10-08 — Owner Authentication Hardening
- Added persistent login guard with five-failure lockout for the Factory 2 owner login endpoint.
- Lock state survives process restarts because it is stored in `gf_auth_guard`.
- Successful authentication clears the guard state.
- Added regression coverage for lockout and reset behavior.
- Latest code/test commits: `c3aff1c9727f5e8d2ac06f34ceed024ee1794282`, `9f8d64ef15b22ab5fb7bb9236022659d1576b6ed`, `b2a8a89a136cd00e7d9be8ffd5df6f89ee8772ea`.


## 2026-10-08 — Session Secret Hardening
- Factory 2 now stores only SHA-256 hashes of bearer session tokens in `gf_sessions`; plaintext session tokens are never persisted.
- Existing persisted sessions are intentionally invalidated by this format change and require a fresh login.
- Added regression coverage proving the returned token authenticates while the stored database value is only a 64-character hash.
- Latest code/test checkpoint: `fe6be8ac81257262454f6e8d83c9e2eef9c28149`, `c63037264af379d8e7c462691cd927cccdfa9163`.
- Local execution could not be completed in this environment because outbound network/DNS is unavailable and the registered remote development device is offline. GitHub source changes are saved.


## 2026-10-08 — External Provider Contract Hardening
- Added explicit provider capability metadata and a registration hook for future official API adapters.
- Base provider remains fail-closed and cannot claim a real publication.
- Provider exceptions now transition a distribution to `FAILED` with sanitized error provenance; invalid provider states are also rejected.
- Added regression coverage for the provider contract.
- Source/test checkpoint: `27b7894e4b4560759408be3d5dd82c44badeaee3`, `6e98e0ffb302cd0ec87675a903af3b24f50fb867`.
- CI workflow status remains unobservable for this push; no successful CI claim made.


## 2026-10-08 — First concrete official provider: VK API
- Current Russian advertising restrictions were rechecked before selecting the first concrete channel. Instagram/Facebook were excluded from the first production path because current Russian advertising restrictions apply to those resources; Factory 2 will not use VPN or other bypasses to automate them.
- Added a concrete **VK official API adapter** with capability metadata for publishing and post-level measurement.
- Publication uses the official `wall.post` API and returns a real VK post identifier when the official API succeeds.
- Measurement uses the official `wall.getById` API and extracts views, likes, comments and reposts as external metrics.
- Tokens are never stored in the Factory 2 database. The database keeps only the credential reference; runtime secret resolution is isolated to the process environment.
- Provider failures are fail-closed and sanitized.
- Added automatic external measurement polling: `SUBMITTED/PUBLISHED → MEASURED` through the provider adapter, with learning after verified measurement.
- Added HTTP endpoint `/factory2/api/distribution/poll`.
- Added regression tests for provider capabilities, secret-reference handling, publication contract, measurement parsing and fail-closed behavior.
- **VK automation is not enabled by default.** Compliance remains YELLOW until an owner-reviewed current rule explicitly permits the required action in the relevant jurisdiction.
- This block does not claim a real publication or live VK smoke test; no production token was used and the execution environment still has no outbound network access.
- Source checkpoints: 92910f11ed153ff7292c5c8bb0e9da0e98b2014f, b1c4ba47d066e8474ecd22e1ef87c5999388cd59, 1a04d869e0fafa900de79a76388551944e199eae, 222330a874b29e5bc42d4bb773b493fd53dc793b, 88527b65d9331a308dea244147a68338995ffb42.


## 2026-10-08 — Verified artifact gate for external publication
- Strengthened the external distribution boundary so a provider receives a verified Factory 2 artifact, not an abstract content id only.
- Before provider publication, Factory 2 now selects a READY image artifact, checks its storage path, MIME type and SHA-256 content hash, and fails closed on missing/not-ready/tampered/unsupported artifacts.
- The provider payload now carries artifact provenance (`artifact_id`, variant, MIME type, storage path, content hash, provider).
- Added regression coverage for the publication artifact boundary.
- This intentionally does **not** claim that VK image upload itself is complete yet: the next block is the official VK photo-upload sequence (`photos.getWallUploadServer` → upload → `photos.saveWallPhoto` → `wall.post`) followed by mocked integration tests.
- Saved checkpoint: `31f6e05673f50166dcebb10da915d88ca0cf221f`, tests `2713778c7289130a0111df4c24a7ed423199b828`.


## 2026-10-08 — Official VK image publication contour

Checkpoint: `821c45631bbd25143db7776e58126b2cef959370`

Completed:
- VK provider now uses the official image publication sequence:
  `photos.getWallUploadServer` → multipart image upload → `photos.saveWallPhoto` → `wall.post` with a `photo{owner_id}_{photo_id}` attachment.
- Publication is fail-closed on missing/not-ready/missing-file/unsupported-MIME/hash-mismatch artifacts.
- Artifact SHA-256 is verified immediately before provider upload.
- Provider provenance records the artifact ID/hash, MIME type, API methods and API version.
- Runtime credentials remain reference-only; the access token is resolved from the runtime environment and is never stored in the Factory 2 database.
- Added regression coverage for the complete mocked VK image sequence, artifact tampering, and missing verified artifact.
- The existing Factory 2 distribution idempotency key remains the duplication guard at the control-plane boundary.
- Measurement polling remains connected to the published VK post through `wall.getById`.

Verification status:
- Code and regression tests were added and saved to GitHub.
- GitHub Actions currently reports no workflow run for this commit, so CI PASS is not claimed.
- No live VK token, live publication, or live external measurement smoke test was performed.
- Current implementation is ready for a controlled live OAuth/API smoke test once an owner-approved VK connection is available.


## 2026-10-08 — Production boundary hardening after VK image contour

Checkpoint: `76c0991a449b108d1a335149ca021843117d083c`

- Centralized verified-artifact validation inside Factory 2 before any external provider is invoked.
- The control plane independently verifies READY state, file existence, declared content hash and actual SHA-256 before handing the artifact to a provider.
- Artifact failures are persisted as sanitized distribution failures.
- This creates defense in depth: Factory 2 validates the artifact and the concrete VK provider validates it again immediately before upload.
- No provider is allowed to receive an unverified image.
- No live publication or production smoke test is claimed; current workflow-run visibility does not provide a CI result for these push commits.


## 2026-10-08 — External publication concurrency hardening

Checkpoint: `e05a309a2528dc334820e7475f5bf60e09741a81`

- Added an atomic `PUBLISHING` claim before invoking an external provider.
- A second concurrent submit for the same distribution can no longer start another provider publication while the first claim is active.
- Existing idempotency keys remain the persistent duplication guard.
- Provider/content/artifact failures remain fail-closed and transition the distribution to `FAILED`.
- Added regression coverage for the concurrent-submit claim boundary.
- This is source-level hardening; no live provider call or production smoke test is claimed.


## 2026-10-08 — Owner session regression hardening

Checkpoint: `18b838f987b67ba2f1235dde066dc094438897cb`

- Added regression coverage proving an expired bearer session is rejected by the Owner authentication boundary.
- Session tokens remain stored only as SHA-256 hashes and expire server-side.
- Remote server verification remains pending because the registered remote development device is currently offline.
- GitHub Actions currently exposes no workflow run for these commits, so CI PASS is not claimed.


## 2026-10-08 — HTTP and verification hardening

Checkpoint after the previous owner-session hardening sequence.

- Hardened the Factory 2 HTTP boundary: malformed JSON and invalid Content-Length are normalized to safe client errors.
- Unexpected server exceptions now return HTTP 500 with a generic `internal_error` response instead of being mislabeled as HTTP 400.
- Existing detailed exception names remain server-side only through the process log; they are not exposed to API clients.
- Added `workflow_dispatch` to the GLOBAL FACTORY 2 CI workflow so the full compile + pytest verification can be started explicitly when GitHub Actions execution is available.
- Current repository source remains saved on `main`.
- A live server verification is still not claimed because the registered remote development device is offline.
- A CI PASS is still not claimed until an actual workflow run reports success.


## 2026-10-08 — JSON request-shape hardening

- Hardened the HTTP request body parser so valid JSON must be a JSON object.
- JSON arrays, scalars, and malformed JSON now fail closed as `invalid_json` client errors instead of reaching route handlers and producing unexpected internal errors.
- Added regression tests for non-object and malformed JSON payloads.
- Source and tests are saved on `main`.
- Full CI execution and live server verification are still not claimed until an actual workflow run or reachable production environment confirms them.


## 2026-10-08 — Production hardening consolidation

Checkpoint after the autonomous hardening pass from `f0952d69e515e36dd80dcdeac718013aaccfe4c0`.

- Bounded bearer authentication input and registration credential lengths.
- Rejected non-standard JSON numeric constants such as NaN/Infinity at the HTTP boundary.
- Growth Fund spending rejects non-finite amounts; external measurements ignore non-finite metrics.
- Verified publication artifacts are limited to 25 MiB and hashed in bounded streaming chunks.
- VK upload URLs are restricted to HTTPS hosts under `vk.com`.
- Added regression coverage for these boundaries.
- CI PASS and live production/server smoke verification remain unclaimed until actually observed.


## 2026-10-08 — Final hardening review

- Rechecked the consolidated hardening against the existing Factory 2 regression suite.
- Adjusted the mocked VK upload endpoint in the regression fixture to use an HTTPS `*.vk.com` host, matching the production upload-target allowlist.
- No live provider call, CI PASS, or production-server PASS is claimed without an actual external execution result.



## 2026-10-10 — VK upload transport hardening

- Disabled automatic HTTP redirects for the VK image-upload request so an upload URL that redirects outside the validated VK host cannot silently redirect the artifact bytes to another host.
- Capped the upload endpoint response body at 1 MiB before JSON parsing.
- This is a source hardening change only; the local test suite, GitHub Actions, and live server have not been executed in this environment, so no PASS is claimed.
- Code checkpoint: 0e4927cc5c1fa5031f31223f163061ca0ff9b4a2.


## 2026-10-10 — VK multipart transport fix and CI checkpoint

Checkpoint: `11bd7070c8491a66c256cd7465d800662c5d5d0b`

- Fixed multipart framing in the VK upload transport: CRLF separators are now actual carriage-return/newline bytes rather than literal backslash sequences.
- The VK API contract test now injects a deterministic upload response instead of contacting an external upload URL; this keeps tests offline and avoids accidental network calls.
- Updated the contract assertion to check for the `wall.post` request independent of call order and to verify the runtime token is used consistently.
- GLOBAL FACTORY 2 CI passed on this checkpoint: `128 passed in 8.08s`; Python compile step also passed.
- CHUMA Server Handoff passed release validation on the same checkpoint.
- CHUMA IP FACTORY CI was still running when this note was written; verify its final status before treating the overall repository checks as green.
- No production deployment, live VK publication, or live server smoke test is claimed. Next step: verify the remaining workflow result, then continue toward a real deployment/health check without enabling external publishing.
