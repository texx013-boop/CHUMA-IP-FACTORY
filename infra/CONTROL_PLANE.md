# CHUMA Control Plane

## Purpose

CHUMA CONTROL is the owner-facing control plane. It is not a GitHub Actions front-end and it must remain operationally independent from GitHub.

## Planes

- **Identity Plane** — Owner identity, trusted sessions, device trust and permissions.
- **Control Plane** — CHUMA CONTROL API, jobs, server registry, modes and operator UX.
- **Execution Plane** — CHUMA Agent and project executors.
- **Runtime Plane** — Docker, systemd, PostgreSQL, storage and network.
- **Code Plane** — Git repositories and version history. GitHub is a code-plane dependency only.
- **Data Plane** — project data, artifacts, backups and provenance.
- **Event Plane** — append-only operational events used by UI, notifications and future automation.

## Job lifecycle

Every remote command becomes a durable Job:

`QUEUED -> DISPATCHED -> RUNNING -> VERIFYING -> SUCCEEDED`

Failure path:

`RUNNING/VERIFYING -> FAILED -> RETRYING | BLOCKED`

Cancellation:

`QUEUED/DISPATCHED/RUNNING -> CANCELLED`

A Job must keep its project, owner session, requested task, mode, timestamps, current stage, result and correlation id.

## Autonomy

- L0: observe only
- L1: supervised execution
- L2: autonomous execution within project permissions
- L3: MAX_AUTONOMOUS_FINISH within the configured risk ceiling
- L4: reserved and disabled

Safe Mode overrides autonomy and prevents new execution locks.

## Security

The external surface exposes only CHUMA CONTROL. SSH, Docker and server administration remain internal capabilities of the Agent. Project executors receive explicit capabilities rather than unrestricted shell access.

## GitHub boundary

GitHub may be used for source, review, CI/CD and rollback references. It must never be required for ordinary runtime control, job dispatch, status, pause, stop or monitoring.

## Future scale

The same Control API can address one or many Agents. Server Registry therefore uses stable server IDs instead of hard-coding provider IP addresses into the control protocol.
