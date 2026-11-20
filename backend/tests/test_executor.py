# Archive-on-done (spec §10.3, AC-1.3, AC-2.1): a message is archived only when every job referencing it
# is final, and only with a verified move. Reference IMAP plugin on GreenMail, the fake plugin for an
# unverified move, real MongoDB.
import asyncio
from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId

from app.executor import JobNotOpen, finish, undo
from app.models.action_log import ActionLogEntry
from app.models.job import Artifacts, Job, Verb
from app.models.message import Message
from app.plugins.registry import PluginRegistry
from app.sync import close_handled_elsewhere
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, PLUGIN, connected, fake_plugin
from tests.utils.mail_server import Mailbox, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def stored(plugin_id: str, ref: str) -> Message:
    message = Message.model_validate(
        {
            "owner_id": OWNER,
            "plugin_id": plugin_id,
            "ref": ref,
            "message_id": ref,
            "sender": {"email": "a@example.com"},
            "to": [],
            "cc": [],
            "date": datetime(2026, 11, 2, tzinfo=UTC),
            "subject": "Invoice",
            "snippet": "",
        }
    )
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
        done = await finish(pay.id, "done", registry, by="owner", level="ask")
        still_in_inbox = subjects(mailbox, "INBOX")
        dismissed = await finish(file.id, "dismissed", registry, by="owner", level=None)

    assert (done.state, done.error) == ("done", None) and still_in_inbox == [ref]
    assert (dismissed.state, dismissed.error) == ("dismissed", None)
    assert subjects(mailbox, "INBOX") == [] and subjects(mailbox, "Archive") == [ref]


@pytest.mark.parametrize(
    ("mode", "error"),
    [
        ("unverified", "fake couldn't confirm the archive, so the message is still in the inbox"),
        ("malformed", "fake couldn't archive the message (it answered outside the contract), so it is still in the inbox"),
    ],
)
async def test_an_unverified_or_garbled_archive_keeps_the_job_open_and_names_the_plugin(test_db, monkeypatch, mode, error):
    """AC-1.3; a reply outside the contract must reopen the job too, never leave it done."""
    monkeypatch.setenv("FAKE_MODE_ARCHIVE", mode)
    monkeypatch.setenv("FAKE_MODE_INBOX", "present")
    job = await job_over(await stored("fake", "r1"))
    plugin = fake_plugin("fake", {"FAKE_ARCHIVE": "FAKE_MODE_ARCHIVE", "FAKE_INBOX_CONTAINS": "FAKE_MODE_INBOX"})
    async with connected(plugin) as registry:
        finished = await finish(job.id, "done", registry, by="owner", level="ask")

    assert (finished.state, finished.error) == ("open", error)


async def test_a_disconnected_plugin_keeps_the_job_open_and_names_it(test_db):
    job = await job_over(await stored("proton", "r1"))

    finished = await finish(job.id, "done", PluginRegistry(), by="owner", level="ask")

    assert (finished.state, finished.error) == ("open", "proton isn't connected, so the message is still in the inbox")


async def test_mail_the_owner_filed_elsewhere_is_left_where_they_put_it(test_db, mailbox: Mailbox):
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    mailbox.create_folder("Archive")
    mailbox.move(ref, "Receipts")
    job = await job_over(await stored(PLUGIN, ref))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        finished = await finish(job.id, "done", registry, by="owner", level="ask")

    assert (finished.state, finished.error) == ("done", None)
    assert subjects(mailbox, "Receipts") == [ref] and subjects(mailbox, "Archive") == []


async def test_a_job_dismissed_earlier_doesnt_hold_the_message(test_db, mailbox: Mailbox):
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    mailbox.create_folder("Archive")
    message = await stored(PLUGIN, ref)
    first, second = await job_over(message), await job_over(message)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await finish(first.id, "dismissed", registry, by="owner", level=None)  # the other one is still open: the message stays
        await finish(second.id, "done", registry, by="owner", level="ask")

    assert subjects(mailbox, "Archive") == [ref]


async def test_only_an_open_job_can_be_finished(test_db):
    job = await job_over(await stored("proton", "r1"))
    await Job.find(Job.id == job.id).update({"$set": {"state": "handled_elsewhere"}})

    with pytest.raises(JobNotOpen):
        await finish(job.id, "done", PluginRegistry(), by="owner", level="ask")


async def test_a_job_reopened_with_an_error_isnt_closed_as_handled_elsewhere(test_db, mailbox: Mailbox):
    """Its error must stay in front of the owner until they retry."""
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    job = await job_over(await stored(PLUGIN, ref))
    await Job.find(Job.id == job.id).update({"$set": {"error": "proton couldn't confirm the archive"}})
    mailbox.move(ref, "Archive")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        closed = await close_handled_elsewhere(OWNER, PLUGIN, registry.clients[PLUGIN])

    reloaded = await Job.get(job.id)
    assert closed == 0 and reloaded is not None and reloaded.state == "open"


async def test_an_interrupted_finish_reopens_the_job(test_db, monkeypatch):
    """E.g. the owner's request is cancelled mid-archive: the job must stay retryable."""
    monkeypatch.setenv("FAKE_MODE_ARCHIVE", "slow")
    monkeypatch.setenv("FAKE_MODE_INBOX", "present")
    job = await job_over(await stored("fake", "r1"))
    plugin = fake_plugin("fake", {"FAKE_ARCHIVE": "FAKE_MODE_ARCHIVE", "FAKE_INBOX_CONTAINS": "FAKE_MODE_INBOX"})
    async with connected(plugin) as registry:
        finishing = asyncio.create_task(finish(job.id, "done", registry, by="owner", level="ask"))
        await asyncio.sleep(1)  # claimed and waiting on the archive
        finishing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await finishing

    reloaded = await Job.get(job.id)
    assert reloaded is not None and reloaded.state == "open"
    assert reloaded.error == "finishing was interrupted, so the message is still in the inbox"


async def test_an_interrupted_finish_still_logs_the_mail_it_archived(test_db, mailbox: Mailbox, monkeypatch):
    """Those messages left the inbox: the history must show them, with their undo."""
    monkeypatch.setenv("FAKE_MODE_ARCHIVE", "slow")
    monkeypatch.setenv("FAKE_MODE_INBOX", "present")
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="x")
    mailbox.create_folder("Archive")
    archived_first, waiting = await stored(PLUGIN, ref), await stored("fake", "r1")
    assert archived_first.id is not None and waiting.id is not None
    job = Job(
        owner_id=OWNER, verb="todo", title="Pay", artifacts=Artifacts(link="https://x.example"), message_ids=[archived_first.id, waiting.id]
    )
    await job.insert()
    plugin = fake_plugin("fake", {"FAKE_ARCHIVE": "FAKE_MODE_ARCHIVE", "FAKE_INBOX_CONTAINS": "FAKE_MODE_INBOX"})
    async with connected(reference_imap_plugin(mailbox), plugin) as registry:
        finishing = asyncio.create_task(finish(job.id, "done", registry, by="owner", level="ask"))
        for _ in range(100):  # the first copy archived, the second waiting on the slow plugin
            if subjects(mailbox, "Archive") == [ref]:
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)
        finishing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await finishing

    [entry] = await ActionLogEntry.find(ActionLogEntry.job_id == job.id).to_list()
    assert (entry.action, entry.message_ids, entry.ok, entry.undoable) == ("archived", [archived_first.id], False, True)
    assert entry.error == "finishing was interrupted, so the message is still in the inbox"


async def test_an_interrupted_undo_releases_its_claim(test_db, monkeypatch):
    """E.g. the owner's request is cancelled mid-restore: the archive must stay undoable."""
    monkeypatch.setenv("FAKE_MODE_RESTORE", "slow")
    monkeypatch.setenv("FAKE_MODE_INBOX", "absent")
    message = await stored("fake", "r1")
    assert message.id is not None
    entry = ActionLogEntry(
        owner_id=OWNER,
        action="archived",
        job_id=PydanticObjectId(),
        message_ids=[message.id],
        by="owner",
        permission_level="ask",
        ok=True,
        undoable=True,
    )
    await entry.insert()
    plugin = fake_plugin("fake", {"FAKE_RESTORE": "FAKE_MODE_RESTORE", "FAKE_INBOX_CONTAINS": "FAKE_MODE_INBOX"})
    async with connected(plugin) as registry:
        undoing = asyncio.create_task(undo(entry, registry))
        await asyncio.sleep(1)  # claimed and waiting on the restore
        undoing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await undoing

    reloaded = await ActionLogEntry.get(entry.id)
    assert reloaded is not None and reloaded.undone is False


async def archived_once_each(*message_ids: PydanticObjectId) -> bool:
    entries = await ActionLogEntry.find(ActionLogEntry.action == "archived").to_list()
    logged = [message_id for entry in entries for message_id in entry.message_ids]
    return sorted(logged) == sorted(message_ids)


async def test_a_digest_that_fails_partway_archives_each_message_once_on_retry(test_db, mailbox: Mailbox):
    """The first try archives what it can and reopens; the retry archives only what is left."""
    work = new_mailbox()
    refs = [mailbox.deliver(sender=f"news{n}@example.com", subject=f"Newsletter {n}", body="x") for n in range(2)]
    late_ref = work.deliver(sender="news@example.com", subject="Newsletter", body="x")
    for account in (mailbox, work):
        account.create_folder("Archive")
    messages = [*[await stored(PLUGIN, ref) for ref in refs], await stored("work-imap", late_ref)]
    message_ids = [message.id for message in messages if message.id is not None]
    digest = Job(owner_id=OWNER, verb="digest", title="Skim", artifacts=Artifacts(digest="a\nb\nc"), message_ids=message_ids)
    await digest.insert()
    async with connected(reference_imap_plugin(mailbox)) as registry:  # the work account isn't connected yet
        failed = await finish(digest.id, "done", registry, by="owner", level="ask")
    async with connected(reference_imap_plugin(mailbox), reference_imap_plugin(work, "work-imap")) as registry:
        retried = await finish(digest.id, "done", registry, by="owner", level="ask")

    assert (failed.state, failed.error) == ("open", "work-imap isn't connected, so the message is still in the inbox")
    assert (retried.state, retried.error) == ("done", None)
    assert subjects(mailbox, "INBOX") == [] and sorted(subjects(mailbox, "Archive")) == sorted(refs)
    assert subjects(work, "INBOX") == [] and subjects(work, "Archive") == [late_ref]
    assert await archived_once_each(*message_ids)


async def test_two_jobs_over_one_message_finishing_at_once_archive_it_once(test_db, mailbox: Mailbox):
    """Both are final, so either may archive it; only one does, and neither reopens."""
    ref = mailbox.deliver(sender="a@example.com", subject="Invoice", body="Pay invoice 4471")
    mailbox.create_folder("Archive")
    message = await stored(PLUGIN, ref)
    pay, file = await job_over(message), await job_over(message, verb="archive_noise")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        finished = await asyncio.gather(*(finish(job.id, "done", registry, by="owner", level="ask") for job in (pay, file)))

    assert [(job.state, job.error) for job in finished] == [("done", None), ("done", None)]
    assert subjects(mailbox, "INBOX") == [] and subjects(mailbox, "Archive") == [ref]
    assert message.id is not None and await archived_once_each(message.id)
