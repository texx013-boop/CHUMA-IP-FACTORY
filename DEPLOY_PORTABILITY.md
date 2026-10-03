# CHUMA IP FACTORY — Portable Deployment

The application is intentionally deployment-provider agnostic.

## Production topology

Application container:
- Dockerfile
- HTTP listener uses `PORT`
- liveness: `/health`
- readiness: `/ready`
- PostgreSQL through `DATABASE_URL`
- persistent media/data under `CHUMA_DATA_DIR` / `CHUMA_MEDIA_DIR`

The same application image can run on Railway, Render, a VPS, or another Docker-compatible platform.

## Render

`render.yaml` defines a production web service, managed PostgreSQL, persistent application disk, health checks, and secret placeholders.

The Blueprint deliberately keeps paid-provider generation disabled by default. Secrets are supplied outside Git through Render's secret configuration.

Render's persistent disk is required because generated media is filesystem-backed. The managed PostgreSQL database stores application state.

## Docker Compose

`docker-compose.yml` provides a complete local/self-hosted topology:
- PostgreSQL 16
- CHUMA application container
- health-gated startup
- persistent named volumes
- application healthcheck

Start:

```bash
docker compose up -d --build
```

Verify:

```bash
curl http://127.0.0.1:8097/health
curl http://127.0.0.1:8097/ready
```

Stop:

```bash
docker compose down
```

Data remains in Docker volumes until those volumes are explicitly removed.

## Railway

Railway remains supported through `railway.toml` and the existing Dockerfile. No Railway-specific business logic is used by the application.

## Migration principle

Do not copy the SQLite database into production when PostgreSQL is available. Configure `DATABASE_URL` and let the application's schema initialization create/upgrade the supported schema.

For media migration, copy the contents of the configured media directory while preserving filenames and verify SHA-256 hashes of important artifacts after transfer.

## Security

Never commit:
- `DATABASE_URL`
- `CHUMA_ADMIN_TOKEN`
- provider API keys
- runtime databases
- generated media
- private provider responses

The production blueprint uses secret placeholders rather than hardcoded credentials.
