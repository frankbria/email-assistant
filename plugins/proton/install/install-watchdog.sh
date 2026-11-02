#!/usr/bin/env bash
# Start the Proton watchdog with your user session (Linux, systemd user unit). Bridge
# runs in your session, so this is a user unit, not a system service.
# Usage: install-watchdog.sh [ENV_FILE]   (default ~/.config/email-assistant/proton.env)
set -euo pipefail

env_file="${1:-$HOME/.config/email-assistant/proton.env}"
plugin_directory="$(cd "$(dirname "$0")/.." && pwd)"
uv="$(command -v uv)"
unit_directory="$HOME/.config/systemd/user"

[[ -f "$env_file" ]] || { echo "Settings file not found: $env_file (copy proton.env.example there and fill it in)." >&2; exit 1; }
mkdir -p "$unit_directory"
cat > "$unit_directory/email-assistant-proton-watchdog.service" <<UNIT
[Unit]
Description=email-assistant Proton watchdog (keeps Bridge and the plugin running)
After=default.target

[Service]
Environment=MAILBOX_ENV_FILE=$env_file
ExecStart=$uv run --directory $plugin_directory python -m proton_plugin.watchdog
Restart=always
RestartSec=60

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now email-assistant-proton-watchdog.service
echo "Installed and started email-assistant-proton-watchdog (starts with your session)."
echo "To run it without an open session too: loginctl enable-linger $USER"
