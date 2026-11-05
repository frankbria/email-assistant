# Changes made outside the app (spec §5.3): a message that left the inbox closes its open jobs.
# Real plugins (reference IMAP on GreenMail, the fake plugin for failures) and real MongoDB; no mocks.
import logging

import pytest

from app.models.job import Artifacts, Job, JobState
from app.models.message import Message
from app.plugins import calls
from app.sync import SyncEngine, SyncError, close_handled_elsewhere
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, add_owner, connected, fake_plugin
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def job_over(message: Message, state: JobState = "open") -> Job:
    assert message.id is not None
    job = Job(owner_id=OWNER, verb="reply", title=message.subject, artifacts=Artifacts(), message_ids=[message.id], state=state)
    await job.insert()
    return job


async def state_of(job: Job) -> JobState:
    stored = await Job.get(job.id)
    assert stored is not None
    return stored.state


@pytest.mark.parametrize("batch", [calls.INBOX_CONTAINS_BATCH, 1])
async def test_a_message_archived_outside_the_app_closes_its_job_on_the_next_poll(test_db, mailbox: Mailbox, monkeypatch, batch):
    monkeypatch.setattr(calls, "INBOX_CONTAINS_BATCH", batch)
    await add_owner(test_db)
    on_phone = [mailbox.deliver(sender="a@example.com", subject=f"Archived on phone {n}", body="x") for n in range(2)]
    still_there = mailbox.deliver(sender="a@example.com", subject="Still in inbox", body="x")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        engine = SyncEngine(registry, test_db["user"], poll_seconds=60)
        await engine.sync_all()
        messages = {message.message_id: message for message in await Message.find_all().to_list()}
        jobs = {message_id: await job_over(message) for message_id, message in messages.items()}
        dismissed = await job_over(messages[on_phone[0]], state="dismissed")
        snoozed = await job_over(messages[on_phone[1]], state="snoozed")  # its mail may be out of the inbox on purpose
        for message_id in on_phone:
            mailbox.move(message_id, "Archive")

        await engine.sync_all()

    assert {message_id: await state_of(job) for message_id, job in jobs.items()} == {
        on_phone[0]: "handled_elsewhere",
        on_phone[1]: "handled_elsewhere",
        still_there: "open",
    }
    assert (await state_of(dismissed), await state_of(snoozed)) == ("dismissed", "snoozed")
    # Archived once, by the owner; the app archived nothing and left the rest alone.
    assert sorted(str(m["Message-ID"]) for m in mailbox.messages("Archive")) == sorted(on_phone)
    assert [str(m["Message-ID"]) for m in mailbox.messages("INBOX")] == [still_there]


async def test_a_digest_lets_go_of_each_newsletter_archived_elsewhere_and_closes_when_none_remain(test_db, mailbox: Mailbox):
    """A digest spans distinct messages: one read and archived on a phone leaves the digest open for the rest."""
    await add_owner(test_db)
    refs = [mailbox.deliver(sender=f"news{n}@example.com", subject=f"Newsletter {n}", body="x") for n in range(3)]
    async with connected(reference_imap_plugin(mailbox)) as registry:
        engine = SyncEngine(registry, test_db["user"], poll_seconds=60)
        await engine.sync_all()
        messages = {message.message_id: message for message in await Message.find_all().to_list()}
        digest = Job(
            owner_id=OWNER,
            verb="digest",
            title="Low-priority mail to skim",
            artifacts=Artifacts(digest="a\nb\nc"),
            message_ids=[messages[ref].id for ref in refs],
        )
        await digest.insert()
        mailbox.move(refs[0], "Archive")

        await engine.sync_all()
        one_gone = await Job.get(digest.id)
        for ref in refs[1:]:
            mailbox.move(ref, "Archive")
        await engine.sync_all()

    assert one_gone is not None and one_gone.state == "open"
    assert one_gone.message_ids == [messages[ref].id for ref in refs[1:]]
    assert await state_of(digest) == "handled_elsewhere"


async def test_only_this_plugins_messages_with_open_jobs_are_checked(test_db, caplog):
    """The fake plugin has no `inbox_contains`, so any call to it would fail the pass."""
    await add_owner(test_db)
    elsewhere = Message.model_validate(
        {
            "owner_id": OWNER,
            "plugin_id": "another-account",
            "ref": "r1",
            "message_id": "<m@x>",
            "sender": {"email": "a@example.com"},
            "to": [],
            "cc": [],
            "date": "2026-11-02T12:00:00Z",
            "subject": "s",
            "snippet": "",
        }
    )
    await elsewhere.insert()
    job = await job_over(elsewhere)
    async with connected(fake_plugin("fake", {})) as registry:
        with caplog.at_level(logging.ERROR):
            await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert await state_of(job) == "open"


async def test_a_failing_inbox_check_raises_with_the_plugins_words_and_closes_nothing(test_db):
    message = Message.model_validate(
        {
            "owner_id": OWNER,
            "plugin_id": "fake",
            "ref": "r1",
            "message_id": "<m@x>",
            "sender": {"email": "a@example.com"},
            "to": [],
            "cc": [],
            "date": "2026-11-02T12:00:00Z",
            "subject": "s",
            "snippet": "",
        }
    )
    await message.insert()
    job = await job_over(message)
    async with connected(fake_plugin("fake", {})) as registry:
        with pytest.raises(SyncError, match="fake.*inbox_contains failed"):
            await close_handled_elsewhere(OWNER, "fake", registry.clients["fake"])

    assert await state_of(job) == "open"


@pytest.mark.parametrize("answer", ["extra", "missing"])
async def test_an_answer_that_is_not_exactly_the_asked_refs_closes_nothing(test_db, monkeypatch, answer):
    monkeypatch.setenv("FAKE_ANSWER", answer)
    message = Message.model_validate(
        {
            "owner_id": OWNER,
            "plugin_id": "fake",
            "ref": "r1",
            "message_id": "<m@x>",
            "sender": {"email": "a@example.com"},
            "to": [],
            "cc": [],
            "date": "2026-11-02T12:00:00Z",
            "subject": "s",
            "snippet": "",
        }
    )
    await message.insert()
    job = await job_over(message)
    async with connected(fake_plugin("fake", {"FAKE_INBOX_CONTAINS": "FAKE_ANSWER"})) as registry:
        with pytest.raises(SyncError, match="fake: inbox_contains answered for other refs"):
            await close_handled_elsewhere(OWNER, "fake", registry.clients["fake"])

    assert await state_of(job) == "open"


async def test_a_typed_plugin_error_names_the_plugin_tool_and_reason(test_db, mailbox: Mailbox):
    message = Message.model_validate(
        {
            "owner_id": OWNER,
            "plugin_id": "reference-imap",
            "ref": "<a@example.com>\r\nA001 LOGOUT",
            "message_id": "<a@example.com>",
            "sender": {"email": "a@example.com"},
            "to": [],
            "cc": [],
            "date": "2026-11-02T12:00:00Z",
            "subject": "s",
            "snippet": "",
        }
    )
    await message.insert()
    job = await job_over(message)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        with pytest.raises(SyncError, match=r"reference-imap: inbox_contains failed: \S"):
            await close_handled_elsewhere(OWNER, "reference-imap", registry.clients["reference-imap"])

    assert await state_of(job) == "open"
