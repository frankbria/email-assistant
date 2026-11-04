"""Gmail over IMAP: refs are X-GM-MSGID, and moves are label changes checked with X-GM-LABELS.

In Gmail, folders are labels and "[Gmail]/All Mail" holds every message. Archiving moves the
message out of INBOX (removes the Inbox label); restoring copies it from All Mail back to INBOX
(adds the label). Nothing is ever moved out of All Mail or expunged: in Gmail that trashes mail.
"""

import imaplib
import re
from email.message import EmailMessage

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from mailbox_contract import Capability, ErrorCode, MailboxInfo, MoveResult

GMAIL_ID = re.compile(rb"X-GM-(MSGID|THRID) (\d+)")
LABEL_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|\)|[^\s()"]+')
INBOX_LABEL = "\\inbox"
# X-GM-MSGID is an unsigned 64-bit integer.
MAX_ID_DIGITS = 20


def gmail_ids(fetch_line: bytes) -> dict[str, str]:
    """{"MSGID": …, "THRID": …} from a FETCH response line."""
    return {name.decode(): value.decode() for name, value in GMAIL_ID.findall(fetch_line)}


def gmail_labels(fetch_response: list[object]) -> set[str]:
    """The labels in an `X-GM-LABELS (…)` FETCH response, lowercased, quotes removed. A label
    sent as a literal shows only as its `{n}` marker: system labels such as \\Inbox never are."""
    line = b" ".join(item[0] if isinstance(item, tuple) else item for item in fetch_response if isinstance(item, (bytes, tuple)))
    _, found, rest = line.partition(b"X-GM-LABELS (")
    if not found:
        raise MailboxError(ErrorCode.UNAVAILABLE, "Gmail didn't return the message's labels.")
    labels = set()
    for token in LABEL_TOKEN.findall(rest):
        if token == b")":
            break
        if token.startswith(b'"'):
            # Only \\ and \" are escapes (RFC 3501); a loosely quoted "\Inbox" keeps its backslash.
            token = re.sub(rb'\\([\\"])', rb"\1", token[1:-1])
        labels.add(token.decode(errors="replace").lower())
    return labels


class GmailMailbox(ImapMailbox):
    FETCH_ITEMS = "(X-GM-MSGID X-GM-THRID BODY.PEEK[])"

    # --- plain-language failures ---------------------------------------------------------

    def login_rejected_message(self, protocol: str) -> str:
        return (
            f"Gmail rejected the {protocol} login. Use an app password (Google Account → Security → "
            "2-Step Verification → App passwords), not your Google password, and check that IMAP is on."
        )

    # --- refs: X-GM-MSGID ----------------------------------------------------------------

    def _add_server_headers(self, message: EmailMessage, fetch_line: bytes) -> None:
        ids = gmail_ids(fetch_line)
        if "MSGID" not in ids:
            raise MailboxError(ErrorCode.UNAVAILABLE, "Gmail didn't return the message's X-GM-MSGID.")
        # Replace any copies the sender put in the mail: only the server's ids count. mailbox/1 has
        # no thread field, so get_message's headers carry X-GM-THRID.
        for name, value in ids.items():
            del message[f"X-GM-{name}"]
            message[f"X-GM-{name}"] = value

    def _ref(self, message: EmailMessage) -> str:
        return str(message["X-GM-MSGID"])

    def _find_uid(self, connection: imaplib.IMAP4, folder: str, ref: str) -> int | None:
        # Anything but an X-GM-MSGID can't name a Gmail message (and never reaches the command).
        if not (ref.isascii() and ref.isdigit() and len(ref) <= MAX_ID_DIGITS):
            return None
        if not self._folder_exists(connection, folder):
            return None
        self._select(connection, folder)
        uids = self._search(connection, "X-GM-MSGID", ref)
        return uids[0] if uids else None

    # --- archive / restore ----------------------------------------------------------------

    def _labels(self, connection: imaplib.IMAP4, ref: str) -> tuple[int, set[str]] | None:
        """The message's UID in All Mail and its labels, or None if it isn't in All Mail."""
        uid = self._find_uid(connection, self.folders.archive, ref)
        if uid is None:
            return None
        status, data = connection.uid("FETCH", str(uid), "(X-GM-LABELS)")
        if status != "OK" or not data:
            raise MailboxError(ErrorCode.UNAVAILABLE, "Gmail didn't return the message's labels.")
        return uid, gmail_labels(data)

    def archive(self, ref: str) -> MoveResult:
        with self._imap() as connection:
            uid = self._find_uid(connection, self.folders.inbox, ref)
            if uid is not None:
                if "MOVE" not in connection.capabilities:
                    raise MailboxError(ErrorCode.UNSUPPORTED, "This server doesn't support IMAP MOVE.")
                self._select(connection, self.folders.inbox, readonly=False)
                status, _ = connection.uid("MOVE", str(uid), f'"{self.folders.archive}"')
                if status != "OK":
                    return MoveResult(ok=False, verified=False)
            found = self._labels(connection, ref)
            if found is None:
                if uid is None:
                    raise MailboxError(ErrorCode.NOT_FOUND, "No message with that ref.")
                return MoveResult(ok=True, verified=False)
            return MoveResult(ok=True, verified=INBOX_LABEL not in found[1])

    def restore(self, ref: str) -> MoveResult:
        with self._imap() as connection:
            found = self._labels(connection, ref)
            if found is None:
                raise MailboxError(ErrorCode.NOT_FOUND, "No message with that ref.")
            uid, labels = found
            if INBOX_LABEL in labels:
                return MoveResult(ok=True, verified=True)  # already in the inbox
            # COPY, not MOVE: moving out of All Mail would trash the message.
            self._select(connection, self.folders.archive, readonly=False)
            status, _ = connection.uid("COPY", str(uid), f'"{self.folders.inbox}"')
            if status != "OK":
                return MoveResult(ok=False, verified=False)
            after = self._labels(connection, ref)
            return MoveResult(ok=True, verified=after is not None and INBOX_LABEL in after[1])

    # --- tools ---------------------------------------------------------------------------

    def mailbox_info(self) -> MailboxInfo:
        return super().mailbox_info().model_copy(update={"capabilities": [Capability.PUSH]})
