#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
install -d -m 0700 "$APP_ROOT/agent/backups"
install -m 0755 "$(dirname "$0")/chuma-agent.sh" "$APP_ROOT/agent/chuma-agent.sh"
install -m 0755 "$(dirname "$0")/agent-backup.sh" "$APP_ROOT/agent/agent-backup.sh"
install -m 0755 "$(dirname "$0")/agent-verify.sh" "$APP_ROOT/agent/agent-verify.sh"
install -m 0755 "$(dirname "$0")/agent-rollback.sh" "$APP_ROOT/agent/agent-rollback.sh"
install -m 0755 "$(dirname "$0")/auto-update.sh" "$APP_ROOT/agent/auto-update.sh"
install -m 0755 "$(dirname "$0")/chuma-watchdog.sh" "$APP_ROOT/agent/chuma-watchdog.sh"
install -m 0755 "$(dirname "$0")/chuma-security-agent.sh" "$APP_ROOT/agent/chuma-security-agent.sh"
install -m 0644 "$(dirname "$0")/chuma-agent.service" /etc/systemd/system/chuma-agent.service
install -m 0644 "$(dirname "$0")/chuma-auto-update.service" /etc/systemd/system/chuma-auto-update.service
install -m 0644 "$(dirname "$0")/chuma-watchdog.service" /etc/systemd/system/chuma-watchdog.service
install -m 0644 "$(dirname "$0")/chuma-security-agent.service" /etc/systemd/system/chuma-security-agent.service
systemctl daemon-reload
systemctl enable --now chuma-agent.service chuma-auto-update.service chuma-watchdog.service chuma-security-agent.service
echo "CHUMA Agent, Watchdog and Security Agent installed and running."
