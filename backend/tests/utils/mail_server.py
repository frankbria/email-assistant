# backend/tests/utils/mail_server.py
"""Seed and inspect real mailboxes on the GreenMail test server (docker-compose.test.yml).

GreenMail runs with auth disabled and creates a mailbox on first use, so every test gets
its own address and never needs cleanup.
"""

import imaplib
import os
import smtplib
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import make_msgid

MAIL_HOST = os.environ.get("MAIL_TEST_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("MAIL_TEST_SMTP_PORT", "3025"))
IMAP_PORT = int(os.environ.get("MAIL_TEST_IMAP_PORT", "3143"))
PASSWORD = "unused"  # auth is disabled on the test server


def wait_until_ready(timeout_seconds: float = 30) -> None:
    """Block until both SMTP and IMAP answer; the port opens before GreenMail is ready."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with smtplib.SMTP(MAIL_HOST, SMTP_PORT, timeout=2) as smtp:
                smtp.noop()
            imaplib.IMAP4(MAIL_HOST, IMAP_PORT, timeout=2).logout()
            return
        except (OSError, imaplib.IMAP4.error):  # imaplib errors aren't OSErrors
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"No test mail server at {MAIL_HOST}:{SMTP_PORT}/{IMAP_PORT}; "
                    "start it with: docker compose -f docker-compose.test.yml up -d"
                ) from None
            time.sleep(0.5)


def build_message(*, sender: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="test.example")
    message.set_content(body)
    return message


@dataclass
class Mailbox:
    address: str

    @contextmanager
    def imap(self) -> Iterator[imaplib.IMAP4]:
        connection = imaplib.IMAP4(MAIL_HOST, IMAP_PORT, timeout=10)
        try:
            connection.login(self.address, PASSWORD)
            yield connection
        finally:
            connection.logout()

    def create_folder(self, folder: str) -> None:
        with self.imap() as connection:
            connection.create(folder)  # "already exists" is fine

    def deliver(self, *, sender: str, subject: str, body: str) -> str:
        """Send a message to this mailbox over SMTP, like real inbound mail; returns its Message-ID."""
        message = build_message(sender=sender, to=self.address, subject=subject, body=body)
        with smtplib.SMTP(MAIL_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(message)
        self._wait_for(message["Message-ID"], "INBOX")
        return message["Message-ID"]

    def append(self, folder: str, *, sender: str, subject: str, body: str, to: str | None = None) -> str:
        """Put a message straight into a folder (Sent, Archive, …) over IMAP; returns its Message-ID."""
        message = build_message(sender=sender, to=to or self.address, subject=subject, body=body)
        with self.imap() as connection:
            connection.create(folder)  # "already exists" is fine
            status, _ = connection.append(folder, None, None, message.as_bytes())
            assert status == "OK", f"APPEND to {folder} failed"
        return message["Message-ID"]

    def messages(self, folder: str) -> list[EmailMessage]:
        """Every message in the folder, oldest first ([] if the folder doesn't exist)."""
        with self.imap() as connection:
            _, listing = connection.list('""', folder)
            if listing == [None]:
                return []
            status, detail = connection.select(folder, readonly=True)
            assert status == "OK", f"SELECT {folder} failed: {detail}"
            _, data = connection.uid("SEARCH", None, "ALL")
            parsed = []
            for uid in data[0].split():
                _, fetched = connection.uid("FETCH", uid, "(RFC822)")
                raw = fetched[0][1]
                assert isinstance(raw, bytes)
                message = message_from_bytes(raw, policy=policy.default)
                assert isinstance(message, EmailMessage)
                parsed.append(message)
            return parsed

    def _wait_for(self, message_id: str, folder: str, timeout_seconds: float = 10) -> None:
        # SMTP delivery is asynchronous on the server side.
        deadline = time.monotonic() + timeout_seconds
        while not any(m["Message-ID"] == message_id for m in self.messages(folder)):
            if time.monotonic() > deadline:
                raise TimeoutError(f"{message_id} never reached {folder}")
            time.sleep(0.1)


def new_mailbox() -> Mailbox:
    return Mailbox(address=f"test-{uuid.uuid4().hex[:12]}@test.example")
