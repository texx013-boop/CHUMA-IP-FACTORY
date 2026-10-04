# CHUMA Autonomous Server Agent

The CHUMA deployment uses a provider-independent autonomous control layer.

## Runtime layers

- **Main Agent** — monitors application health and performs safe service recovery.
- **Auto Update Agent** — detects new repository revisions, snapshots the current release, validates the candidate, deploys it and restores the previous release when health verification fails.
- **Watchdog** — monitors the Main Agent and Auto Update Agent and restarts them if they stop; it also keeps a separate application health timestamp.
- **Security Agent** — periodically checks protected configuration permissions, removes accidental Git metadata from releases, scans releases for common private-key/token markers, and verifies that the core agent services remain enabled.
- **Control** — provides operator-oriented status, logs, health, restart, update and backup actions.

## Safety model

Automated changes must preserve owner control, safe mode and rollback. The update path creates a pre-change snapshot before deployment. A failed candidate must not replace a healthy previous release when a previous release is available.

## State and logs

Operational state is stored under /opt/chuma/agent with restrictive permissions. Important state markers include deployed_sha, last_healthy, watchdog_last_healthy and security_last_audit. Logs are kept in the same protected directory.

## Provider independence

Selectel is only the current infrastructure adapter. The agent does not require a provider-specific API.

## Current autonomous sequence

1. detect repository revision;
2. create a pre-change snapshot;
3. download and validate the candidate release;
4. preserve the current release;
5. deploy the candidate;
6. wait for health;
7. keep the candidate only after successful verification;
8. otherwise restore the previous release;
9. refresh the autonomous services;
10. continuously monitor and self-recover.

## Important production boundary

Repository and server deployment access are separate concerns. The server-side updater currently consumes the public main branch. No GitHub private key is stored on the server. If the repository is made private later, the updater must be changed to an authenticated artifact/release mechanism before private deployment is enabled.
