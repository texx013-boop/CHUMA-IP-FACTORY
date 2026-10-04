# CHUMA Deployment Core

Reusable VPS infrastructure for CHUMA IP FACTORY and future Combain projects.

## Target

The deployment core is intentionally provider-independent:

- Ubuntu/Debian VPS
- Docker Engine + Compose
- Caddy reverse proxy with automatic HTTPS
- isolated project networks
- persistent project volumes
- PostgreSQL kept private
- scheduled PostgreSQL and volume backups
- no secrets committed to Git
- optional future Redis/worker services

The VPS is the control/orchestration layer. GPU-heavy rendering and paid AI generation remain external adapters.

## Layout

```
VPS
├── /opt/chuma/infra
│   ├── compose.yml
│   ├── Caddyfile
│   ├── .env
│   └── backups/
├── chuma-ip-factory
│   ├── app
│   ├── postgres
│   └── persistent data
└── future-combains
    └── isolated project stacks
```

## Bootstrap

1. Provision a small VPS (initial target: 4 vCPU / 8 GB RAM / 80+ GB SSD).
2. Install Docker Engine and Compose plugin.
3. Copy `infra/compose.yml`, `infra/Caddyfile`, and `infra/.env.example` to `/opt/chuma/infra`.
4. Create `.env` with strong random secrets.
5. Point DNS records at the VPS.
6. Start the stack:

```bash
docker compose --env-file .env -f compose.yml config
docker compose --env-file .env -f compose.yml up -d
```

7. Verify:

```bash
docker compose ps
curl -fsS https://$CHUMA_DOMAIN/ready
```

## Security baseline

- Do not expose PostgreSQL publicly.
- Do not put API keys in Git.
- Use a unique long random admin token.
- Expose only ports 80/443 at the VPS firewall.
- Keep SSH on a non-default policy only if key-based access is already working.
- Enable automatic security updates.
- Keep backups outside the application container.
- Review backup restoration periodically.

This repository contains the deployment template only. It does **not** contain VPS credentials or perform the external provider purchase/login step.
## First VPS deployment

The first production deployment intentionally requires one external setup action: the VPS must receive a production `infra/.env` containing the real domain, database password and CHUMA admin token. This file is never committed to Git and is preserved across application releases.

After the server bootstrap is complete, deployment is performed by the manually triggered GitHub Actions workflow. The workflow uploads a source release only; it does not contain or retrieve production secrets from the repository.

For the first deployment, keep the existing portable Operator SSH key for human administration. The separate CI/CD Deployment Key is optional until automated deployment is activated.

## Backup policy

The scheduled backup creates atomic PostgreSQL dumps locally under `infra/backups/`. Local backups are not a disaster-recovery substitute. Before declaring production complete, configure an off-site copy and perform at least one restore test on an isolated database.
