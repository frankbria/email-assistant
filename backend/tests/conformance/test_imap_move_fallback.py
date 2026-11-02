# The reference plugin's archive/restore on a server without MOVE: COPY, then UID EXPUNGE
# of that one message. GreenMail supports MOVE, so the capability is hidden here.
import imaplib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from mailbox_contract import ErrorCode
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


class MailboxWithoutMoveOrUidplus(ImapMailbox):
    @contextmanager
    def _imap(self) -> Iterator[imaplib.IMAP4]:
        with super()._imap() as connection:
            connection.capabilities = tuple(c for c in connection.capabilities if c not in ("MOVE", "UIDPLUS"))
            yield connection


def settings_for(mailbox: Mailbox) -> ImapMailboxSettings:
    return ImapMailboxSettings(
        account=mailbox.address, username=mailbox.address, password="unused", tls="none",
        imap_host=MAIL_HOST, imap_port=IMAP_PORT, smtp_host=MAIL_HOST, smtp_port=SMTP_PORT,
    )


def test_without_move_or_uidplus_archive_refuses_and_changes_nothing(mailbox: Mailbox):
    mailbox.append("Archive", sender="setup@example.com", subject="folder setup", body="x")
    ref = mailbox.deliver(sender="ana@example.com", subject="stays put", body="x")

    with pytest.raises(MailboxError) as refused:
        MailboxWithoutMoveOrUidplus(settings_for(mailbox)).archive(ref)

    assert refused.value.code == ErrorCode.UNSUPPORTED
    [inbox_message] = mailbox.messages("INBOX")
    assert inbox_message["Message-ID"] == ref
    assert ref not in {str(m["Message-ID"]) for m in mailbox.messages("Archive")}


@pytest.mark.parametrize("ref", ["<a@example.com>\r\nA001 LOGOUT", "<a@example.com>\n", "<a\x00@example.com>"])
def test_refs_with_control_characters_are_rejected(mailbox: Mailbox, ref: str):
    plugin = ImapMailbox(settings_for(mailbox))

    for action in (plugin.get_message, plugin.archive, plugin.restore):
        with pytest.raises(MailboxError) as rejected:
            action(ref)
        assert rejected.value.code == ErrorCode.INVALID_ARGUMENT
