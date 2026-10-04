# CHUMA Portable Key Architecture

## Purpose

CHUMA infrastructure must survive VPS replacement, migration between providers, and addition of new Combain projects without replacing the operator's identity.

## Key classes

### 1. Operator SSH Key - portable

The operator key is the primary human administration identity.

- The same public key may be installed on every CHUMA server.
- The private key stays under the operator's control.
- Never commit or upload the private key to Git.
- Never copy the private key onto a server.
- When a VPS is replaced, install the same public key on the new VPS.
- The current operator key created for the first CHUMA server is an Ed25519 key and is intended to remain portable.

### 2. Deployment Key - CI/CD only

A separate Ed25519 key is used by GitHub Actions to reach deployment targets.

- Private key is stored only as a GitHub Actions secret.
- Public key is installed in the server account used for deployment.
- The VPS never stores a GitHub repository-access key.
- The Deployment Key must not be reused as an operator key.
- The key can be rotated without changing the operator's access.

### 3. Server Host Keys - non-portable

Every VPS keeps its own SSH host identity.

- Never copy a host private key between servers.
- Host keys protect server identity and must change when a machine is replaced.
- The operator's SSH client maintains known-host verification for each server.

### 4. Recovery

Maintain an offline recovery copy of the Operator private key and its passphrase in a secure password manager or encrypted offline storage.

Recovery material must never be placed in GitHub, the VPS filesystem, project archives, or chat.

## Standard

Every future CHUMA / Combain server follows:

1. Install the portable Operator public key.
2. Create a dedicated deployment account.
3. Install the CI/CD Deployment public key only on that deployment account.
4. Give deployment account only the permissions required for Docker deployment.
5. Keep GitHub repository credentials off the server.
6. Keep server host keys unique.
7. Rotate Deployment Keys independently of Operator Keys.

## Migration

For a new VPS:

- provision the server;
- install the same Operator public key;
- install the current Deployment public key;
- run the deployment pipeline;
- verify HTTPS, health, persistence and backups;
- revoke the old server's Deployment public key if the old VPS is retired.

No application identity or database secret should depend on an individual VPS SSH key.

## Current CHUMA principle

Identity follows CHUMA, not the server.

The VPS is replaceable infrastructure. The operator identity, deployment process, application secrets and recovery procedure are portable layers above it.
