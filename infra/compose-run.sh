#!/usr/bin/env bash
set -euo pipefail

# Portable Compose launcher: prefer the modern plugin, fall back to legacy docker-compose.
if docker compose version >/dev/null 2>&1; then
  docker compose "$@"
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose "$@"
else
  echo "CHUMA: Docker Compose is not installed." >&2
  exit 127
fi
