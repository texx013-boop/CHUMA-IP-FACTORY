# CHUMA IP FACTORY

Private repository for the CHUMA IP FACTORY / CHUMA OS implementation.

## Current baseline

- Architecture: Master Architecture 2.0
- Image-first production strategy
- Owner is not the daily operator
- Current verified image-factory milestone: 2.5.3
- External provider integrations remain explicitly disconnected until authorized
- Cloud runtime: Railway
- Current production smoke test: public HTTP UI online

## Repository policy

No secrets, runtime databases, media, credentials, or generated private artifacts belong in Git.

## Deployment target

Railway cloud deployment, with provider-agnostic application contracts and external service authorization handled separately.
