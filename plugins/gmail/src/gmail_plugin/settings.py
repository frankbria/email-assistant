from typing import Any, Literal

from imap_mailbox.settings import ImapMailboxSettings
from pydantic import field_validator, model_validator


class GmailSettings(ImapMailboxSettings):
    """MAILBOX_ACCOUNT (the Gmail address) and MAILBOX_PASSWORD (an app password) from the
    environment; everything else defaults to Gmail's servers and folder names."""

    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    tls: Literal["ssl", "starttls", "none"] = "ssl"
    # English names; other interface languages (and "[Google Mail]" accounts) set MAILBOX_FOLDER_*.
    folder_archive: str = "[Gmail]/All Mail"
    folder_sent: str = "[Gmail]/Sent Mail"
    plugin_name: str = "gmail"

    @model_validator(mode="before")
    @classmethod
    def gmail_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("username") and data.get("account"):
                data["username"] = data["account"]  # Gmail signs in with the address
            if str(data.get("smtp_port")) == "587" and not data.get("smtp_tls"):
                data["smtp_tls"] = "starttls"  # 587 is submission with STARTTLS; 465 is implicit TLS
        return data

    @field_validator("tls", "imap_tls", "smtp_tls")
    @classmethod
    def require_encryption(cls, mode: str | None) -> str | None:
        if mode == "none":
            raise ValueError("Gmail connections must use TLS (ssl or starttls)")
        return mode
