# CHUMA CONTROL — Platform Architecture

CHUMA CONTROL is the server-side control plane for the user's projects. GitHub is a source and code-history provider, not the production authority.

## Operating model

OWNER → CHUMA CONTROL → PROJECT AGENTS → CHUMA SERVER → DATA / MEDIA / BACKUPS

Projects include SHUMA.SPACE, Film Combain, Personal AI Companion and future projects.

## Responsibilities

- project registry and lifecycle state;
- release selection and promotion;
- health and readiness policy;
- deployment orchestration;
- rollback coordination;
- backup/restore policy;
- security policy;
- audit trail;
- provider-agnostic integration boundaries.

## GitHub role

GitHub remains useful for source-code history, external code backup, CI, review, reproducible source retrieval and optional open-source distribution. It must not be the only source of truth for runtime state.

## Source strategy

CHUMA CONTROL is designed to accept releases from a remote source such as GitHub and from a verified local handoff bundle. This allows production operation to survive a temporary GitHub outage and keeps the source provider replaceable.

## Project isolation

Every project gets an independent identifier, configuration/secrets, containers, data/storage, health checks, backup policy, rollback point and audit events. Private secrets and writable application volumes are never shared between projects.

## Recovery principle

**IDENTITY FOLLOWS CHUMA, NOT THE SERVER.** A replacement VPS must be able to restore the control plane, project releases, configuration and backups without rebuilding the architecture manually.

## Migration direction

The current GitHub-driven updater remains compatible during migration. The next integration step is to make CHUMA CONTROL the deployment authority and keep GitHub as one source adapter.

A production deployment is accepted only after server-side health and rollback verification.
