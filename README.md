# CHUMA IP FACTORY / SHUMA.SPACE

Private repository for the CHUMA IP FACTORY / SHUMA.SPACE implementation.

## Current baseline

- User-facing product: **SHUMA.SPACE**
- Internal core: **CHUMA IP FACTORY**
- Version: **2.5.8**
- Architecture: Master Architecture 2.0
- Image-first production strategy
- Owner is not the daily operator
- Zero-budget-first spending policy: free by default, paid generation requires explicit opt-in
- No subscriptions or automatic provider upgrades
- Durable autonomous job queue with idempotency, retries and dead-letter handling
- Background worker for non-blocking cycle execution
- External image-provider retry/backoff with persisted provider-run outcomes
- Liveness and database readiness endpoints
- External provider integrations remain explicitly disconnected until authorized

## Character control

The product supports controlled user influence over a character:

- provide or edit character DNA;
- randomize DNA through the factory;
- choose a synthetic/generated voice;
- attach a user's own voice asset;
- preserve character identity and provenance across generated content.

## Image → Video Combain

Video is a modular extension of the image-first core.

Current Video Combain capabilities:

- create a video job from an existing image-content item;
- create a video job automatically from the latest READY image-content item for a character;
- preserve owner_id, character_id, source_content_id and source_asset_ids provenance;
- use a free test-manifest engine for deterministic pipeline validation;
- connect an external video renderer through an explicit API adapter;
- block unconfigured external engines;
- respect the global zero-budget policy;
- retry transient provider failures;
- enforce provider response and output-size limits;
- validate external video URLs before download;
- reject embedded URL credentials;
- deduplicate repeated image → video requests;
- persist jobs across restart;
- write rendered artifacts atomically through a temporary file and rename;
- verify source-artifact filesystem containment and SHA-256 integrity immediately before rendering;
- verify the final artifact with SHA-256 before marking it READY;
- expose the latest image → video flow directly in SHUMA.SPACE.

The external renderer is intentionally an adapter boundary: SHUMA.SPACE does not depend on one specific video provider.

## Production policy

The system is designed to proceed autonomously after the user has configured the required account/provider credentials. External authorization, API keys and paid-provider opt-in remain explicit user-controlled actions.

## Repository policy

No secrets, runtime databases, media, credentials, or generated private artifacts belong in Git.

## Deployment targets

Provider-agnostic Docker deployment. Railway remains supported as a fallback; Render production infrastructure is defined in `render.yaml`; a complete self-hosted PostgreSQL topology is defined in `docker-compose.yml`. Application contracts do not depend on a specific cloud provider.

## Verification rule

A feature is considered complete only after:

1. implementation;
2. automated tests;
3. failure-path checks;
4. repeat verification;
5. build/CI verification;
6. saving the verified result to the repository.

Current Video Combain hardening includes tests for image → video chaining, idempotency, restart persistence, provider response/base64/output-size limits, URL validation, and atomic artifact integrity.

### Security / tenant isolation
- Owner-scoped API resources require `X-Owner-ID` matching the resource owner.
- Owner listing is itself scoped and never returns other owners' characters.
- Artifact downloads verify owner scope, filesystem containment, and SHA-256 integrity before serving bytes.
- Video Combain validates character/content/artifact provenance both at job creation and again immediately before rendering.
- Video job listing supports an owner-scoped `character_id` filter and rejects foreign-character filters.

## Autonomous server runtime

The production server is designed to run as an autonomous control loop:

- CHUMA Agent performs health recovery;
- Auto Update Agent tracks the private GitHub repository through a dedicated read-only SSH deploy key;
- Watchdog restarts failed agent services;
- Security Agent checks runtime permissions and credential-like material;
- daily PostgreSQL backups run through systemd and retain integrity hashes;
- failed deployments restore the previous release and verify health before accepting the result;
- runtime secrets remain outside Git.

The GitHub repository remains private. The server-side updater therefore never downloads source through a public archive URL; it requires its dedicated repository read key. GitHub deploy keys are repository-scoped and can be read-only.
