#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/opt/chuma}"
INFRA_DIR="${APP_ROOT}/infra"
AGENT_DIR="${APP_ROOT}/agent"

install -d -m 0700 "$AGENT_DIR/backups"
install -m 0755 "$INFRA_DIR/chuma-agent.sh" "$AGENT_DIR/chuma-agent.sh"
install -m 0755 "$INFRA_DIR/agent-backup.sh" "$AGENT_DIR/agent-backup.sh"
install -m 0755 "$INFRA_DIR/agent-verify.sh" "$AGENT_DIR/agent-verify.sh"
install -m 0755 "$INFRA_DIR/agent-rollback.sh" "$AGENT_DIR/agent-rollback.sh"
install -m 0755 "$INFRA_DIR/auto-update.sh" "$AGENT_DIR/auto-update.sh"
install -m 0755 "$INFRA_DIR/chuma-watchdog.sh" "$AGENT_DIR/chuma-watchdog.sh"
install -m 0755 "$INFRA_DIR/chuma-security-agent.sh" "$AGENT_DIR/chuma-security-agent.sh"
install -m 0755 "$INFRA_DIR/github-access.sh" "$AGENT_DIR/github-access.sh"
install -m 0755 "$INFRA_DIR/backup-verify.sh" "$AGENT_DIR/backup-verify.sh"
install -m 0755 "$INFRA_DIR/chuma-control.sh" "$AGENT_DIR/chuma-control.sh"

install -m 0644 "$INFRA_DIR/chuma-agent.service" /etc/systemd/system/chuma-agent.service
install -m 0644 "$INFRA_DIR/chuma-auto-update.service" /etc/systemd/system/chuma-auto-update.service
install -m 0644 "$INFRA_DIR/chuma-watchdog.service" /etc/systemd/system/chuma-watchdog.service
install -m 0644 "$INFRA_DIR/chuma-security-agent.service" /etc/systemd/system/chuma-security-agent.service
install -m 0644 "$INFRA_DIR/chuma-backup.service" /etc/systemd/system/chuma-backup.service
install -m 0644 "$INFRA_DIR/chuma-backup.timer" /etc/systemd/system/chuma-backup.timer
install -m 0644 "$INFRA_DIR/chuma-control.service" /etc/systemd/system/chuma-control.service
install -m 0644 "$INFRA_DIR/chuma-control.timer" /etc/systemd/system/chuma-control.timer

systemctl daemon-reload
systemctl enable --now chuma-agent.service chuma-auto-update.service chuma-watchdog.service chuma-security-agent.service
systemctl enable --now chuma-backup.timer chuma-control.timer

echo "CHUMA Agent, Watchdog, Security Agent, Backup Timer and Control Timer installed and running."
