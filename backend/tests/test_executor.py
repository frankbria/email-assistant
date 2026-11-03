# Archive-on-done (spec §10.3, AC-1.3, AC-2.1): a message is archived only when every job referencing it
# is final, and only with a verified move. Reference IMAP plugin on GreenMail, the fake plugin for an
# unverified move, real MongoDB.
from datetime import UTC, datetime

import pytest

from app.executor import JobNotOpen, finish
from app.models.job import Artifacts, Job, Verb
from app.models.message import Message
from app.plugins.registry import PluginRegistry
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, PLUGIN, connected, fake_plugin
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def stored(plugin_id: str, ref: str) -> Message:
    message = Message.model_validate({
        "owner_id": OWNER, "plugin_id": plugin_id, "ref": ref, "message_id": ref, "sender": {"email": "a@example.com"},
        "to": [], "cc": [], "date": datetime(2026, 11, 2, tzinfo=UTC), "subject": "Invoice", "snippet": "",
    })
    await message.insert()
    return message


async def job_over(message: Message, verb: Verb = "todo") -> Job:
    assert message.id is not None
    job = Job(owner_id=OWNER, verb=verb, title="Pay the invoice", artifacts=Artifacts(link="https://x.example"), message_ids=[message.id])
    await job.insert()
    return job


def subjects(mailbox: Mailbox, folder: str) -> list[str]:
    return [str(message["Message-ID"]) for message in mailbox.messages(folder)]


async def test_a_message_stays_until_every_job_on_it_is_final(test_db, mailbox: Mailbox):
    """AC-2.1; the todo is completed by the owner's tap (finish ... done)."""
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="Pay invoice 4471")
    mailbox.create_folder("Archive")
    message = await stored(PLUGIN, ref)
    pay, file = await job_over(message), await job_over(message, verb="archive_noise")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        done = await finish(pay.id, "done", registry)
        still_in_inbox = subjects(mailbox, "INBOX")
        dismissed = await finish(file.id, "dismissed", registry)

    assert (done.state, done.error) == ("done", None) and still_in_inbox == [ref]
    assert (dismissed.state, dismissed.error) == ("dismissed", None)
    assert subjects(mailbox, "INBOX") == [] and subjects(mailbox, "Archive") == [ref]


async def test_an_unverified_archive_keeps_the_job_open_and_names_the_plugin(test_db, monkeypatch):
    """AC-1.3."""
    monkeypatch.setenv("FAKE_MODE_ARCHIVE", "unverified")
    monkeypatch.setenv("FAKE_MODE_INBOX", "present")
    job = await job_over(await stored("fake", "r1"))
    plugin = fake_plugin("fake", {"FAKE_ARCHIVE": "FAKE_MODE_ARCHIVE", "FAKE_INBOX_CONTAINS": "FAKE_MODE_INBOX"})
    async with connected(plugin) as registry:
        finished = await finish(job.id, "done", registry)

    assert finished.state == "open"
    assert finished.error == "fake couldn't confirm the archive, so the message is still in the inbox"


async def test_a_disconnected_plugin_keeps_the_job_open_and_names_it(test_db):
    job = await job_over(await stored("proton", "r1"))

    finished = await finish(job.id, "done", PluginRegistry())

    assert (finished.state, finished.error) == ("open", "proton isn't connected, so the message is still in the inbox")


async def test_mail_the_owner_filed_elsewhere_is_left_where_they_put_it(test_db, mailbox: Mailbox):
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    mailbox.create_folder("Archive")
    mailbox.move(ref, "Receipts")
    job = await job_over(await stored(PLUGIN, ref))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        finished = await finish(job.id, "done", registry)

    assert (finished.state, finished.error) == ("done", None)
    assert subjects(mailbox, "Receipts") == [ref] and subjects(mailbox, "Archive") == []


async def test_a_job_dismissed_earlier_doesnt_hold_the_message(test_db, mailbox: Mailbox):
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    mailbox.create_folder("Archive")
    message = await stored(PLUGIN, ref)
    first, second = await job_over(message), await job_over(message)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await finish(first.id, "dismissed", registry)  # the other one is still open: the message stays
        await finish(second.id, "done", registry)

    assert subjects(mailbox, "Archive") == [ref]


async def test_only_an_open_job_can_be_finished(test_db):
    job = await job_over(await stored("proton", "r1"))
    await Job.find(Job.id == job.id).update({"$set": {"state": "handled_elsewhere"}})

    with pytest.raises(JobNotOpen):
        await finish(job.id, "done", PluginRegistry())
