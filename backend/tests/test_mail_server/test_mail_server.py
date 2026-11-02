# The containerized IMAP/SMTP test server (GreenMail): seed and inspect real mailboxes.
from tests.utils.mail_server import Mailbox


def test_message_sent_over_smtp_reads_back_over_imap(mailbox: Mailbox):
    message_id = mailbox.deliver(sender="ana@example.com", subject="Q3 budget", body="Can we meet Thursday?")

    [message] = mailbox.messages("INBOX")

    assert message["Message-ID"] == message_id
    assert message["Subject"] == "Q3 budget"
    assert message["From"] == "ana@example.com"
    assert message.get_content().strip() == "Can we meet Thursday?"


def test_sent_and_archive_folders_can_be_seeded(mailbox: Mailbox):
    mailbox.append("Sent", sender=mailbox.address, to="ana@example.com", subject="Re: Q3 budget", body="Thursday works.")
    mailbox.append("Archive", sender="news@example.com", subject="Weekly digest", body="Old news.")

    assert [m["Subject"] for m in mailbox.messages("Sent")] == ["Re: Q3 budget"]
    assert [m["Subject"] for m in mailbox.messages("Archive")] == ["Weekly digest"]
    assert mailbox.messages("INBOX") == []


def test_each_test_gets_an_empty_mailbox(mailbox: Mailbox):
    assert mailbox.messages("INBOX") == []
