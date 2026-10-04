#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
install -d -m 0700 "$APP_ROOT/agent/backups"
install -m 0755 "$(dirname "$0")/chuma-agent.sh" "$APP_ROOT/agent/chuma-agent.sh"
install -m 0755 "$(dirname "$0")/agent-backup.sh" "$APP_ROOT/agent/agent-backup.sh"
install -m 0755 "$(dirname "$0")/agent-verify.sh" "$APP_ROOT/agent/agent-verify.sh"
install -m 0644 "$(dirname "$0")/chuma-agent.service" /etc/systemd/system/chuma-agent.service
systemctl daemon-reload
systemctl enable --now chuma-agent.service
echo "CHUMA Agent installed and running."
