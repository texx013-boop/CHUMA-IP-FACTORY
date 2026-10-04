#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/chuma}"
KEY="${GITHUB_DEPLOY_KEY:-$APP_ROOT/agent/github_deploy_ed25519}"
PUB="${KEY}.pub"
KNOWN="${GITHUB_KNOWN_HOSTS:-$APP_ROOT/agent/github_known_hosts}"

[[ -f "$PUB" ]] || { echo "GitHub deploy public key is not initialized." >&2; exit 2; }
chmod 600 "$KEY"
chmod 644 "$PUB"
echo "GitHub deploy key status:"
echo "  private: $KEY"
echo "  public:  $PUB"
echo
echo "PUBLIC KEY (safe to add to GitHub Deploy Keys):"
cat "$PUB"
echo
if [[ -s "$KNOWN" ]]; then echo "GitHub host key: configured"; else echo "GitHub host key: MISSING"; fi
