"""mailbox/1 over IMAP and SMTP. Never deletes: archive and restore are verified moves."""

import imaplib
import logging
import re
import smtplib
import ssl
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, make_msgid, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Literal

from mailbox_contract import (
    CONTRACT_VERSION,
    Address,
    AttachmentMeta,
    ErrorCode,
    Folders,
    Header,
    Health,
    HealthCheck,
    InboxContainsOutput,
    ListMessagesOutput,
    MailboxInfo,
    MessageDetail,
    MessageSummary,
    MoveResult,
    RepairResult,
    SendResult,
)

from imap_mailbox.settings import ImapMailboxSettings

logger = logging.getLogger(__name__)

SNIPPET_LENGTH = 200
# Refs travel into IMAP SEARCH; a CR/LF would end the command and start another.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class MailboxError(Exception):
    """A failure the plugin reports as a mailbox/1 ToolError."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TextExtractor(HTMLParser):
    """HTML → plain text for messages without a text part."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    extractor = TextExtractor()
    extractor.feed(html)
    return re.sub(r"\s+\n", "\n", "".join(extractor.parts)).strip()


def addresses(message: EmailMessage, header: str) -> list[Address]:
    return [
        Address(name=name or None, email=email)
        for name, email in getaddresses(message.get_all(header, []))
        if email
    ]


def body_text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    return html_to_text(content) if part.get_content_type() == "text/html" else content


class ImapMailbox:
    def __init__(self, settings: ImapMailboxSettings) -> None:
        self.settings = settings
        self.folders = Folders(
            inbox=settings.folder_inbox, archive=settings.folder_archive, sent=settings.folder_sent
        )

    # --- plain-language failures (providers override these) ---------------------------

    def unreachable_message(self, protocol: str, host: str, port: int) -> str:
        return f"Can't reach the {protocol} server at {host}:{port}."

    def untrusted_certificate_message(self, protocol: str, error: ssl.SSLError) -> str:
        return f"The {protocol} server's certificate wasn't trusted ({error.reason})."

    def login_rejected_message(self, protocol: str) -> str:
        return f"The {protocol} server rejected the login."

    def handshake_failed_message(self, protocol: str, host: str, port: int) -> str:
        return (
            f"The {protocol} server at {host}:{port} didn't respond as expected. "
            "Check the port and the security setting (STARTTLS or SSL)."
        )

    # --- connections -----------------------------------------------------------------

    def _tls_context(self) -> ssl.SSLContext:
        # A pinned CA (e.g. Proton Bridge's exported certificate) replaces the system store.
        return ssl.create_default_context(cafile=self.settings.ca_cert_path)

    @contextmanager
    def _imap(self) -> Iterator[imaplib.IMAP4]:
        host, port = self.settings.imap_host, self.settings.imap_port
        tls = self.settings.imap_tls or self.settings.tls
        try:
            if tls == "ssl":
                connection: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, ssl_context=self._tls_context(), timeout=15)
            else:
                connection = imaplib.IMAP4(host, port, timeout=15)
                if tls == "starttls":
                    connection.starttls(ssl_context=self._tls_context())
        except ssl.SSLCertVerificationError as error:
            raise MailboxError(ErrorCode.UNAVAILABLE, self.untrusted_certificate_message("IMAP", error)) from error
        except (ssl.SSLError, TimeoutError, imaplib.IMAP4.error) as error:
            # A TLS/plaintext mismatch shows up as a stall or a garbled greeting.
            raise MailboxError(ErrorCode.UNAVAILABLE, self.handshake_failed_message("IMAP", host, port)) from error
        except OSError as error:
            raise MailboxError(ErrorCode.UNAVAILABLE, self.unreachable_message("IMAP", host, port)) from error
        try:
            connection.login(self.settings.username, self.settings.password)
        except imaplib.IMAP4.error as error:
            with suppress(Exception):
                connection.logout()
            raise MailboxError(ErrorCode.AUTH_FAILED, self.login_rejected_message("IMAP")) from error
        try:
            yield connection
        finally:
            with suppress(Exception):
                connection.logout()

    @contextmanager
    def _smtp(self) -> Iterator[smtplib.SMTP]:
        host, port = self.settings.smtp_host, self.settings.smtp_port
        tls = self.settings.smtp_tls or self.settings.tls
        try:
            if tls == "ssl":
                connection: smtplib.SMTP = smtplib.SMTP_SSL(host, port, context=self._tls_context(), timeout=15)
            else:
                connection = smtplib.SMTP(host, port, timeout=15)
                if tls == "starttls":
                    connection.starttls(context=self._tls_context())
            if self.settings.smtp_login:
                connection.login(self.settings.username, self.settings.password)
        except smtplib.SMTPAuthenticationError as error:
            raise MailboxError(ErrorCode.AUTH_FAILED, self.login_rejected_message("SMTP")) from error
        except ssl.SSLCertVerificationError as error:
            raise MailboxError(ErrorCode.UNAVAILABLE, self.untrusted_certificate_message("SMTP", error)) from error
        except (ssl.SSLError, TimeoutError, smtplib.SMTPServerDisconnected) as error:
            raise MailboxError(ErrorCode.UNAVAILABLE, self.handshake_failed_message("SMTP", host, port)) from error
        except (OSError, smtplib.SMTPException) as error:
            raise MailboxError(ErrorCode.UNAVAILABLE, self.unreachable_message("SMTP", host, port)) from error
        try:
            yield connection
        finally:
            with suppress(Exception):
                connection.quit()

    # --- helpers ---------------------------------------------------------------------

    @staticmethod
    def _select(connection: imaplib.IMAP4, folder: str, readonly: bool = True) -> None:
        status, detail = connection.select(f'"{folder}"', readonly=readonly)
        if status != "OK":
            raise MailboxError(ErrorCode.UNAVAILABLE, f"Can't open folder {folder}: {detail}")

    @staticmethod
    def _search(connection: imaplib.IMAP4, *criteria: str) -> list[int]:
        status, data = connection.uid("SEARCH", *criteria)
        if status != "OK":
            raise MailboxError(ErrorCode.INTERNAL, f"IMAP SEARCH failed: {data}")
        return sorted(int(uid) for uid in data[0].split()) if data and data[0] else []

    @staticmethod
    def _folder_exists(connection: imaplib.IMAP4, folder: str) -> bool:
        status, listing = connection.list('""', f'"{folder}"')
        return status == "OK" and listing != [None]

    def _find_uid(self, connection: imaplib.IMAP4, folder: str, ref: str) -> int | None:
        if not ref.isascii() or CONTROL_CHARACTERS.search(ref) or len(ref) > 998:
            raise MailboxError(ErrorCode.INVALID_ARGUMENT, "That ref isn't a valid message reference.")
        if not self._folder_exists(connection, folder):
            return None
        self._select(connection, folder)
        # shortcut: the ref is the Message-ID header (stable across moves, unlike UIDs); a
        # Message-ID present twice in one folder resolves to the oldest copy. Providers with a
        # stable server id (Gmail X-GM-MSGID) should override this.
        uids = self._search(connection, "HEADER", "Message-ID", f'"{ref}"')
        return uids[0] if uids else None

    @staticmethod
    def _fetch(connection: imaplib.IMAP4, uid: int) -> EmailMessage:
        status, data = connection.uid("FETCH", str(uid), "(BODY.PEEK[])")
        raw = data[0][1] if status == "OK" and data and isinstance(data[0], tuple) else None
        if not isinstance(raw, bytes):
            # Not "not found": the message was just located; this is a server or link failure.
            raise MailboxError(ErrorCode.UNAVAILABLE, "The IMAP server didn't return the message.")
        message = message_from_bytes(raw, policy=policy.default)
        assert isinstance(message, EmailMessage)
        return message

    @staticmethod
    def _summary(message: EmailMessage) -> MessageSummary:
        message_id = str(message["Message-ID"] or "")
        date_header = message["Date"]
        return MessageSummary(
            ref=message_id,
            message_id=message_id,
            sender=(addresses(message, "From") or [Address(email="")])[0],
            to=addresses(message, "To"),
            cc=addresses(message, "Cc"),
            date=parsedate_to_datetime(str(date_header)) if date_header else datetime.now().astimezone(),
            subject=str(message["Subject"] or ""),
            snippet=" ".join(body_text(message).split())[:SNIPPET_LENGTH],
            list_id=str(message["List-Id"]) if message["List-Id"] else None,
            in_reply_to=str(message["In-Reply-To"]) if message["In-Reply-To"] else None,
        )

    def _move(self, ref: str, source: str, target: str) -> MoveResult:
        with self._imap() as connection:
            uid = self._find_uid(connection, source, ref)
            if uid is None:
                if self._find_uid(connection, target, ref) is not None:
                    return MoveResult(ok=True, verified=True)  # already there
                raise MailboxError(ErrorCode.NOT_FOUND, "No message with that ref.")
            if "MOVE" not in connection.capabilities and "UIDPLUS" not in connection.capabilities:
                # Without UID EXPUNGE, removing the source could expunge other messages too.
                raise MailboxError(
                    ErrorCode.UNSUPPORTED, "This IMAP server supports neither MOVE nor UIDPLUS, so it can't move mail safely."
                )
            self._select(connection, source, readonly=False)
            if "MOVE" in connection.capabilities:
                status, _ = connection.uid("MOVE", str(uid), f'"{target}"')
            else:
                # COPY, confirm the copy exists, then expunge only that UID (UIDPLUS).
                status, _ = connection.uid("COPY", str(uid), f'"{target}"')
                if status == "OK":
                    if self._find_uid(connection, target, ref) is None:
                        return MoveResult(ok=False, verified=False)  # source untouched
                    self._select(connection, source, readonly=False)
                    status, _ = connection.uid("STORE", str(uid), "+FLAGS.SILENT", r"(\Deleted)")
                    if status == "OK":
                        status, _ = connection.uid("EXPUNGE", str(uid))
            if status != "OK":
                return MoveResult(ok=False, verified=False)
            # Re-read both folders: the move counts only if it is visible.
            arrived = self._find_uid(connection, target, ref) is not None
            gone = self._find_uid(connection, source, ref) is None
            return MoveResult(ok=True, verified=arrived and gone)

    # --- tools ---------------------------------------------------------------------

    def mailbox_info(self) -> MailboxInfo:
        return MailboxInfo(
            contract_version=CONTRACT_VERSION,
            plugin_name=self.settings.plugin_name,
            plugin_version=self.settings.plugin_version,
            account=self.settings.account,
            capabilities=[],
            folders=self.folders,
        )

    def health(self) -> Health:
        checks = []
        for layer, check in (("imap_login", self._imap), ("smtp", self._smtp)):
            try:
                with check():
                    pass
                checks.append(HealthCheck(layer=layer, ok=True, detail="ok"))
            except MailboxError as error:
                checks.append(HealthCheck(layer=layer, ok=False, detail=error.message))
        failing = [check for check in checks if not check.ok]
        status: Literal["ok", "degraded", "down"] = (
            "ok" if not failing else "down" if len(failing) == len(checks) else "degraded"
        )
        return Health(status=status, checks=checks, repair_actions=[])

    def list_messages(
        self, folder: Literal["inbox", "sent"], cursor: str | None, since: datetime | None, limit: int
    ) -> ListMessagesOutput:
        folder_name = self.folders.inbox if folder == "inbox" else self.folders.sent
        with self._imap() as connection:
            self._select(connection, folder_name)
            validity = str(connection.response("UIDVALIDITY")[1][0], "ascii")
            if cursor is not None:
                cursor_validity, _, last = cursor.partition(":")
                if cursor_validity != validity or not last.isdigit():
                    raise MailboxError(ErrorCode.INVALID_CURSOR, "The cursor no longer matches this folder.")
                after = int(last)
                # "UID n:*" always returns the newest message, even below n; filter it.
                uids = [uid for uid in self._search(connection, "UID", f"{after + 1}:*") if uid > after]
            else:
                criteria = ("SINCE", since.strftime("%d-%b-%Y")) if since else ("ALL",)
                uids = self._search(connection, *criteria)
                after = 0
            page = uids[:limit]
            messages = [self._summary(self._fetch(connection, uid)) for uid in page]
            if page:
                last_uid = page[-1]
            elif cursor is not None:
                last_uid = after
            else:
                # Nothing matched: start after everything currently in the folder.
                everything = self._search(connection, "ALL")
                last_uid = everything[-1] if everything else 0
        return ListMessagesOutput(
            messages=messages, next_cursor=f"{validity}:{last_uid}", has_more=len(uids) > limit
        )

    def inbox_contains(self, refs: list[str]) -> InboxContainsOutput:
        with self._imap() as connection:
            return InboxContainsOutput(
                {ref: self._find_uid(connection, self.folders.inbox, ref) is not None for ref in refs}
            )

    def get_message(self, ref: str) -> MessageDetail:
        with self._imap() as connection:
            for folder in (self.folders.inbox, self.folders.archive, self.folders.sent):
                uid = self._find_uid(connection, folder, ref)
                if uid is not None:
                    message = self._fetch(connection, uid)
                    return MessageDetail(
                        **self._summary(message).model_dump(),
                        headers=[Header(name=name, value=str(value)) for name, value in message.items()],
                        text=body_text(message),
                        attachments=[
                            AttachmentMeta(
                                name=part.get_filename() or "attachment",
                                content_type=part.get_content_type(),
                                size=len(part.get_payload(decode=True) or b""),
                            )
                            for part in message.iter_attachments()
                        ],
                    )
        raise MailboxError(ErrorCode.NOT_FOUND, "No message with that ref.")

    def repair(self, action: str) -> RepairResult:
        """Providers with a `repair` capability override this."""
        raise MailboxError(ErrorCode.UNSUPPORTED, "This plugin has no repair actions.")

    def archive(self, ref: str) -> MoveResult:
        return self._move(ref, self.folders.inbox, self.folders.archive)

    def restore(self, ref: str) -> MoveResult:
        return self._move(ref, self.folders.archive, self.folders.inbox)

    def send(
        self,
        to: list[Address],
        cc: list[Address],
        subject: str,
        body_text: str,
        in_reply_to_ref: str | None,
    ) -> SendResult:
        message = EmailMessage()
        message["From"] = self.settings.account
        message["To"] = ", ".join(address.email for address in to)
        if cc:
            message["Cc"] = ", ".join(address.email for address in cc)
        message["Subject"] = subject
        message["Date"] = format_datetime(datetime.now().astimezone())
        message["Message-ID"] = make_msgid(domain=self.settings.account.partition("@")[2] or None)
        if in_reply_to_ref is not None:
            original = self.get_message(in_reply_to_ref)
            references = next((h.value for h in original.headers if h.name.lower() == "references"), "")
            message["In-Reply-To"] = original.message_id
            message["References"] = f"{references} {original.message_id}".strip()
        message.set_content(body_text)
        with self._smtp() as smtp:
            try:
                smtp.send_message(message)
            except smtplib.SMTPException as error:
                raise MailboxError(ErrorCode.UNAVAILABLE, f"The SMTP server refused the message: {error}") from error
        if self.settings.append_sent:
            # The mail went out; failing now would invite a duplicate send, so only log.
            try:
                with self._imap() as connection:
                    status, detail = connection.append(f'"{self.folders.sent}"', r"(\Seen)", None, message.as_bytes())
                if status != "OK":
                    logger.warning("Sent, but saving a copy to %s failed: %s", self.folders.sent, detail)
            except Exception:
                logger.exception("Sent, but saving a copy to %s failed", self.folders.sent)
        return SendResult(ok=True, sent_message_id=str(message["Message-ID"]))
