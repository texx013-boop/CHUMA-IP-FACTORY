# CHUMA IP FACTORY — Cloud Deployment

The repository is prepared for provider-independent Docker deployment. Railway remains supported, while `render.yaml` defines a Render production topology and `docker-compose.yml` defines a self-hosted PostgreSQL topology.

Runtime:
- Python 3.12
- Dockerfile build
- HTTP server binds to 0.0.0.0
- PORT is read from the environment
- /health is the health endpoint
- SQLite is the local fallback
- DATABASE_URL enables PostgreSQL through psycopg
- CHUMA_ADMIN_TOKEN enables Bearer authentication
- external image generation remains disconnected until explicitly configured

No secrets are committed. Configure credentials as deployment environment variables.


Production persistence:
- PostgreSQL is supported through DATABASE_URL and should be the durable database for production.
- Media files use CHUMA_MEDIA_DIR; when SQLite/local media are used on Railway, mount a persistent Volume at /data or move media to S3-compatible object storage.
- Cloud service filesystems are normally ephemeral between deployments; persistent state therefore requires a persistent disk/volume or external database/object storage. The Render blueprint attaches `/data` for application media.
- The application exposes /health for liveness and /ready for database readiness.
- Autonomous cycles can be submitted to POST /jobs and are processed by the built-in worker with retry/dead-letter semantics.
