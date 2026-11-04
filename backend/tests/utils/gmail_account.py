# backend/tests/utils/gmail_account.py
"""A disposable Gmail account standing in for a GreenMail mailbox, for the live conformance run.

Opt in with GMAIL_ADDRESS and GMAIL_APP_PASSWORD (an app password, never your Google password).
Use an account you can lose: the suite archives everything in its inbox before each test.
"""

import imaplib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

from tests.utils.mail_server import Mailbox, build_message

ADDRESS_ENV, APP_KEY_ENV = "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"
GMAIL_ADDRESS = os.environ.get(ADDRESS_ENV, "")
GMAIL_APP_KEY = os.environ.get(APP_KEY_ENV, "")
# The suite's folder names → Gmail's (English interface).
FOLDERS = {"Archive": "[Gmail]/All Mail", "Sent": "[Gmail]/Sent Mail"}


@dataclass
class GmailAccount(Mailbox):
    password: str = ""

    @contextmanager
    def imap(self) -> Iterator[imaplib.IMAP4]:
        connection = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
        try:
            connection.login(self.address, self.password)
            yield connection
        finally:
            connection.logout()

    def create_folder(self, folder: str) -> None:
        """Gmail already has its archive (All Mail) and Sent."""

    def deliver(self, *, sender: str, subject: str, body: str) -> str:
        """Arrives in the inbox: an APPEND, since mail sent from outside would need a second account."""
        return self.append("INBOX", sender=sender, subject=subject, body=body)

    def append(
        self, folder: str, *, sender: str, subject: str, body: str, to: str | None = None, received: datetime | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        message = build_message(sender=sender, to=to or self.address, subject=subject, body=body)
        for name, value in (headers or {}).items():
            message[name] = value
        with self.imap() as connection:
            status, _ = connection.append(f'"{FOLDERS.get(folder, folder)}"', None, received, message.as_bytes())
            assert status == "OK", f"APPEND to {folder} failed"
        return message["Message-ID"]

    def messages(self, folder: str) -> list[EmailMessage]:
        return super().messages(f'"{FOLDERS.get(folder, folder)}"')

    def empty_inbox(self) -> None:
        """Archive (never delete) everything in the inbox, so each test starts from an empty one."""
        with self.imap() as connection:
            status, detail = connection.select("INBOX")
            assert status == "OK", f"SELECT INBOX failed: {detail}"
            _, found = connection.uid("SEARCH", None, "ALL")
            if found and found[0]:
                status, detail = connection.uid("MOVE", "1:*", f'"{FOLDERS["Archive"]}"')
                assert status == "OK", f"Emptying the inbox failed: {detail}"


def gmail_account() -> GmailAccount:
    account = GmailAccount(address=GMAIL_ADDRESS, password=GMAIL_APP_KEY)
    account.empty_inbox()
    return account
