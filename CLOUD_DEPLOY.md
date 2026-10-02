# CHUMA IP FACTORY — Cloud Deployment

The repository is prepared for Railway-style Docker deployment.

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
