# CHUMA IP FACTORY

Private repository for the CHUMA IP FACTORY / CHUMA OS implementation.

## Current baseline

- Architecture: Master Architecture 2.0
- Image-first production strategy
- Owner is not the daily operator
- Current production milestone: 2.5.5
- Zero-budget-first spending policy: free by default, paid generation requires explicit opt-in
- No subscriptions or automatic provider upgrades
- Durable autonomous job queue with idempotency, retries and dead-letter handling
- Background worker for non-blocking cycle execution
- External image-provider retry/backoff with persisted provider-run outcomes
- Liveness and database readiness endpoints
- External provider integrations remain explicitly disconnected until authorized
- Zero-budget-first: Hugging Face routed inference is the default AI path when a token is supplied; paid generation remains OFF unless explicitly enabled
- No monthly subscription is required; Hugging Face documents a small monthly free credit for free users, and extra usage requires purchased credits
- Cloud runtime: Railway
- Current production smoke test: public HTTP UI online

## Repository policy

No secrets, runtime databases, media, credentials, or generated private artifacts belong in Git.

## Deployment target

Railway cloud deployment, with provider-agnostic application contracts and external service authorization handled separately.

## 2.5.7

Reference-driven image generation is wired for Hugging Face image-to-image providers. Character reference assets are preserved in provenance and can drive new content generation when Hugging Face is connected.
