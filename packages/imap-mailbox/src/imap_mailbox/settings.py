from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ImapMailboxSettings(BaseSettings):
    """Read from the environment (the app passes secrets via plugins.yaml env_from)."""

    model_config = SettingsConfigDict(env_prefix="MAILBOX_")

    account: str = Field(description="The mailbox address.")
    username: str
    password: str
    imap_host: str = "127.0.0.1"
    imap_port: int = 993
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 465
    smtp_login: bool = True
    tls: Literal["ssl", "starttls", "none"] = "ssl"
    imap_tls: Literal["ssl", "starttls", "none"] | None = Field(default=None, description="Overrides tls for IMAP.")
    smtp_tls: Literal["ssl", "starttls", "none"] | None = Field(default=None, description="Overrides tls for SMTP.")
    ca_cert_path: str | None = Field(default=None, description="Pin this CA instead of the system store.")
    folder_inbox: str = "INBOX"
    folder_archive: str = "Archive"
    folder_sent: str = "Sent"
    append_sent: bool = Field(default=False, description="Save sent mail to Sent (when the server doesn't).")
    plugin_name: str = "imap"
    plugin_version: str = "0.1.0"
