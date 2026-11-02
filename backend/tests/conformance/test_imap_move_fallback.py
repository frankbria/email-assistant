# The reference plugin's archive/restore on a server without MOVE: COPY, then UID EXPUNGE
# of that one message. GreenMail supports MOVE, so the capability is hidden here.
import imaplib
from collections.abc import Iterator
from contextlib import contextmanager

from imap_mailbox.mailbox import ImapMailbox
from imap_mailbox.settings import ImapMailboxSettings
from tests.utils.mail_server import IMAP_PORT, MAIL_HOST, SMTP_PORT, Mailbox


class MailboxWithoutMove(ImapMailbox):
    @contextmanager
    def _imap(self) -> Iterator[imaplib.IMAP4]:
        with super()._imap() as connection:
            connection.capabilities = tuple(c for c in connection.capabilities if c != "MOVE")
            yield connection


def test_archive_and_restore_without_move_keep_every_message(mailbox: Mailbox):
    mailbox.append("Archive", sender="setup@example.com", subject="folder setup", body="x")
    keep = mailbox.deliver(sender="ana@example.com", subject="stays", body="x")
    ref = mailbox.deliver(sender="ana@example.com", subject="moves", body="x")
    plugin = MailboxWithoutMove(
        ImapMailboxSettings(
            account=mailbox.address, username=mailbox.address, password="unused", tls="none",
            imap_host=MAIL_HOST, imap_port=IMAP_PORT, smtp_host=MAIL_HOST, smtp_port=SMTP_PORT,
        )
    )

    archived = plugin.archive(ref)
    archived_ids = [str(m["Message-ID"]) for m in mailbox.messages("Archive")]
    restored = plugin.restore(ref)

    assert archived.ok and archived.verified and ref in archived_ids
    assert restored.ok and restored.verified
    # Only the moved message was expunged from INBOX; its neighbour is untouched.
    assert {str(m["Message-ID"]) for m in mailbox.messages("INBOX")} == {keep, ref}
