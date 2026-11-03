# Executing reply and forward jobs (spec §4, AC-2.2): the owner approves, the plugin sends, and only a
# successful send lets the message be archived. Reference IMAP plugin on GreenMail; real MongoDB.
import asyncio
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest

from app.executor import JobNotOpen, execute, forward_subject, reply_subject
from app.models.job import Artifacts, Job, Verb
from app.models.message import Message
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, PLUGIN, connected, fake_plugin
from tests.utils.mail_server import Mailbox, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
CANT_SEND = {"MAILBOX_SMTP_PORT": "1"}  # nothing listens there: IMAP works, every send fails


async def job_for(mailbox: Mailbox, sender: Mailbox, verb: Verb, artifacts: Artifacts) -> tuple[Job, str]:
    ref = sender.deliver_to(mailbox, subject="Q4 budget", body="Could we meet Thursday at 3pm?")
    mailbox.create_folder("Archive")
    message = Message.model_validate({
        "owner_id": OWNER, "plugin_id": PLUGIN, "ref": ref, "message_id": ref, "sender": {"email": sender.address},
        "to": [{"email": mailbox.address}], "cc": [], "date": datetime.now(UTC), "subject": "Q4 budget", "snippet": "",
    })
    await message.insert()
    assert message.id is not None
    job = Job(owner_id=OWNER, verb=verb, title="Ana asks to meet", evidence=["Could we meet Thursday at 3pm?"],
              artifacts=artifacts, message_ids=[message.id])
    await job.insert()
    return job, ref


def received(mailbox: Mailbox) -> list[EmailMessage]:
    return mailbox.messages("INBOX")


async def test_an_approved_reply_goes_threaded_to_the_sender_and_the_mail_is_archived(test_db, mailbox: Mailbox):
    ana = new_mailbox()
    job, ref = await job_for(mailbox, ana, "reply", Artifacts(options=["Thursday works.", "Can't make it."]))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        executed = await execute(job.id, registry, body="Thursday at 3 works. See you then!")

    [reply] = received(ana)
    assert (executed.state, executed.error) == ("done", None)
    assert reply["Subject"] == "Re: Q4 budget" and reply["In-Reply-To"] == ref
    assert "Thursday at 3 works. See you then!" in reply.get_content()
    assert received(mailbox) == [] and [m["Message-ID"] for m in mailbox.messages("Archive")] == [ref]


async def test_a_reply_whose_send_fails_stays_open_to_retry_and_isnt_archived(test_db, mailbox: Mailbox):
    """AC-2.2; then a retry with a working plugin goes through."""
    ana = new_mailbox()
    job, ref = await job_for(mailbox, ana, "reply", Artifacts(draft="Thursday works."))
    async with connected(reference_imap_plugin(mailbox, **CANT_SEND)) as registry:
        failed = await execute(job.id, registry)

    assert failed.state == "failed" and failed.error is not None and failed.error.startswith("send failed — retry")
    assert [m["Message-ID"] for m in received(mailbox)] == [ref] and received(ana) == []
    async with connected(reference_imap_plugin(mailbox)) as registry:
        retried = await execute(job.id, registry)
    assert (retried.state, retried.error) == ("done", None) and len(received(ana)) == 1


async def test_an_approved_forward_carries_the_original_to_the_confirmed_recipient(test_db, mailbox: Mailbox):
    ana, legal = new_mailbox(), new_mailbox()
    job, ref = await job_for(mailbox, ana, "forward", Artifacts(draft="Can you check this?", forward_to="someone@else.example"))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        executed = await execute(job.id, registry, forward_to=legal.address)

    [forward] = received(legal)
    assert executed.state == "done" and forward["Subject"] == "Fwd: Q4 budget"
    text = forward.get_content()
    assert "Can you check this?" in text and "Could we meet Thursday at 3pm?" in text and f"From: {ana.address}" in text
    assert received(mailbox) == []


async def test_a_forward_without_a_recipient_the_owner_chose_sends_nothing(test_db, mailbox: Mailbox):
    """The AI's suggestion alone isn't the owner's confirmation (forward is never autonomous)."""
    job, ref = await job_for(mailbox, new_mailbox(), "forward", Artifacts(draft="FYI", forward_to="legal@example.com"))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        failed = await execute(job.id, registry)

    assert (failed.state, failed.error) == ("failed", "send failed — retry: choose who to forward it to")
    assert [m["Message-ID"] for m in received(mailbox)] == [ref]


async def test_only_open_or_failed_reply_and_forward_jobs_execute(test_db, mailbox: Mailbox):
    job, _ = await job_for(mailbox, new_mailbox(), "todo", Artifacts(link="https://x.example"))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        with pytest.raises(ValueError, match="only reply and forward jobs send"):
            await execute(job.id, registry)
        await Job.find(Job.id == job.id).update({"$set": {"verb": "reply", "state": "done"}})
        with pytest.raises(JobNotOpen):
            await execute(job.id, registry, body="hi")


@pytest.mark.parametrize("body", ["", "   "])
async def test_an_empty_reply_is_never_sent(test_db, mailbox: Mailbox, body: str):
    """The owner cleared the draft: that's not a request to send the draft, nor an empty mail."""
    ana = new_mailbox()
    job, _ = await job_for(mailbox, ana, "reply", Artifacts(draft="Thursday works."))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        failed = await execute(job.id, registry, body=body)

    assert (failed.state, failed.error) == ("failed", "send failed — retry: write the reply first") and received(ana) == []


async def test_a_send_that_went_through_is_never_repeated_when_only_the_archive_failed(test_db):
    """Sent, then the archive failed (no Archive folder): retrying only archives."""
    owner, ana = new_mailbox(), new_mailbox()
    ref = ana.deliver_to(owner, subject="Q4 budget", body="Could we meet?")
    message = Message.model_validate({
        "owner_id": OWNER, "plugin_id": PLUGIN, "ref": ref, "message_id": ref, "sender": {"email": ana.address},
        "to": [], "cc": [], "date": datetime.now(UTC), "subject": "Q4 budget", "snippet": "",
    })
    await message.insert()
    assert message.id is not None
    job = Job(owner_id=OWNER, verb="reply", title="t", artifacts=Artifacts(draft="Yes!"), message_ids=[message.id])
    await job.insert()
    async with connected(reference_imap_plugin(owner)) as registry:
        first = await execute(job.id, registry)
        owner.create_folder("Archive")
        retried = await execute(job.id, registry)

    assert first.state == "open" and first.error is not None and first.sent_at is not None
    assert (retried.state, retried.error) == ("done", None)
    assert len(received(ana)) == 1


async def test_an_interrupted_send_ends_retryable(test_db, monkeypatch):
    monkeypatch.setenv("FAKE_MODE_SEND", "slow")
    message = Message.model_validate({
        "owner_id": OWNER, "plugin_id": "fake", "ref": "<r@x>", "message_id": "<r@x>", "sender": {"email": "a@example.com"},
        "to": [], "cc": [], "date": datetime.now(UTC), "subject": "s", "snippet": "",
    })
    await message.insert()
    assert message.id is not None
    job = Job(owner_id=OWNER, verb="reply", title="t", artifacts=Artifacts(draft="Yes"), message_ids=[message.id])
    await job.insert()
    async with connected(fake_plugin("fake", {"FAKE_SEND": "FAKE_MODE_SEND"})) as registry:
        sending = asyncio.create_task(execute(job.id, registry))
        await asyncio.sleep(1)
        sending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sending

    reloaded = await Job.get(job.id)
    assert reloaded is not None and (reloaded.state, reloaded.error) == ("failed", "send failed — retry: interrupted before it finished")


async def test_a_send_claim_left_by_a_crashed_process_can_be_retried(test_db, mailbox: Mailbox):
    ana = new_mailbox()
    job, _ = await job_for(mailbox, ana, "reply", Artifacts(draft="Thursday works."))
    stale = datetime.now(UTC) - timedelta(minutes=30)
    await Job.find(Job.id == job.id).update({"$set": {"state": "sending", "sending_since": stale}})
    async with connected(reference_imap_plugin(mailbox)) as registry:
        executed = await execute(job.id, registry)

    assert executed.state == "done" and len(received(ana)) == 1


def test_reply_and_forward_subjects_keep_existing_prefixes():
    assert reply_subject("RE: Budget") == "RE: Budget" and reply_subject("Budget") == "Re: Budget"
    assert forward_subject("FW: Budget") == "FW: Budget" and forward_subject("") == "Fwd: (no subject)"
