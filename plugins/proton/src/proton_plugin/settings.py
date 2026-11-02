import ipaddress
import os
from typing import Literal

from pydantic import Field, field_validator

from imap_mailbox.settings import ImapMailboxSettings


# Tailscale assigns addresses from these ranges; anything else could be a LAN or public interface.
TAILSCALE_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


class ProtonSettings(ImapMailboxSettings):
    """Bridge defaults: 127.0.0.1, IMAP 1143 and SMTP 1025, STARTTLS (check Bridge's
    mailbox settings; either side can be switched to SSL there)."""

    imap_host: str = "127.0.0.1"
    imap_port: int = 1143
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    tls: Literal["ssl", "starttls", "none"] = "starttls"
    ca_cert_path: str = Field(description="Bridge's exported cert.pem; verification is never disabled.")
    plugin_name: str = "proton"
    http_host: str | None = Field(default=None, description="The machine's Tailscale IP, for HTTP mode.")
    http_port: int = 8765
    http_token: str | None = Field(default=None, description="Bearer token the app must send in HTTP mode.")
    bridge_restart_command: list[str] | None = Field(
        default=None,
        description='How to restart Bridge, as a JSON list (e.g. ["systemctl", "--user", "restart", "proton-bridge"]). Enables repair.',
    )
    repair_wait_seconds: int = Field(default=60, description="How long repair waits for Bridge to answer again.")
    watchdog_port: int = Field(default=8766, description="Watchdog status endpoint port (on http_host).")
    watchdog_token: str | None = Field(default=None, description="Bearer token for the watchdog status endpoint.")

    @field_validator("tls", "imap_tls", "smtp_tls")
    @classmethod
    def require_encryption(cls, mode: str | None) -> str | None:
        if mode == "none":
            raise ValueError("Bridge connections must use TLS (starttls or ssl)")
        return mode

    @field_validator("http_host")
    @classmethod
    def require_tailscale_or_loopback(cls, host: str | None) -> str | None:
        if host is None:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is None or not (address.is_loopback or any(address in network for network in TAILSCALE_NETWORKS)):
            raise ValueError("bind HTTP mode to this machine's Tailscale IP (100.64.0.0/10 or fd7a:115c:a1e0::/48), or loopback")
        return host


def load_settings() -> ProtonSettings:
    """Settings from the environment, plus MAILBOX_ENV_FILE if set (how the logon task and the
    systemd unit pass them; the plugin process inherits the variable from the watchdog)."""
    return ProtonSettings(_env_file=os.environ.get("MAILBOX_ENV_FILE"))  # type: ignore[call-arg]  # required fields come from env
