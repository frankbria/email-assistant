#!/usr/bin/env bash
# Stop and remove the Proton watchdog user unit.
set -euo pipefail
unit="email-assistant-proton-watchdog.service"
systemctl --user disable --now "$unit" 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/$unit"
systemctl --user daemon-reload
echo "Removed $unit."
