# snooze and follow_up (spec §4): a job hidden until a date comes back then; a follow-up comes back only
# when nobody answered. Time-controlled: the clock is passed in. Real MongoDB; GreenMail for archiving.
from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId
from beanie.operators import In

from app.executor import JobNotOpen, defer, wake, wake_due
from app.models.job import Artifacts, Job, Verb
from app.models.message import Message
from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from app.sync import SyncEngine, close_handled_elsewhere
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, PLUGIN, add_owner, connected
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
NOV_2 = datetime(2026, 11, 2, 9, tzinfo=UTC)
DUE = datetime(2026, 11, 9, 9, tzinfo=UTC)


async def message(ref: str, sender: str, folder: str = "inbox", in_reply_to: str | None = None, date: datetime = NOV_2,
                  to: str = "frank@example.com") -> Message:
    stored = Message.model_validate({
        "owner_id": OWNER, "plugin_id": PLUGIN, "folder": folder, "ref": ref, "message_id": ref, "sender": {"email": sender},
        "to": [{"email": to}], "cc": [], "date": date, "subject": "Contract", "snippet": "", "in_reply_to": in_reply_to,
    })
    await stored.insert()
    return stored


async def job_over(source: Message, verb: Verb, due: datetime | None = DUE) -> Job:
    assert source.id is not None
    job = Job(owner_id=OWNER, verb=verb, title="Contract from Ana", artifacts=Artifacts(), due=due, message_ids=[source.id])
    await job.insert()
    return job


async def state(job: Job) -> tuple[str, str | None]:
    stored = await Job.get(job.id)
    assert stored is not None
    return stored.state, stored.reminder


async def test_a_snoozed_job_reappears_at_its_date(test_db):
    job = await job_over(await message("<m@x>", "ana@example.com"), "snooze")

    await defer(job.id)
    await wake_due(OWNER, PluginRegistry(), now=DUE - timedelta(hours=1))
    before = await state(job)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert before == ("snoozed", None)
    assert await state(job) == ("open", None)


async def test_a_follow_up_fires_when_nobody_answered(test_db):
    original = await message("<m@x>", "ana@example.com")
    await message("<reply@frank>", "frank@example.com", folder="sent", in_reply_to="<m@x>", to="ana@example.com")
    job = await job_over(original, "follow_up")

    await defer(job.id)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert await state(job) == ("open", "No answer from ana@example.com to “Contract” since 2026-11-02")


async def test_a_follow_up_with_an_answer_is_done_and_its_mail_archived(test_db, mailbox: Mailbox):
    ref = mailbox.deliver(sender="ana@example.com", subject="Contract", body="Please sign")
    mailbox.create_folder("Archive")
    original = await message(ref, "ana@example.com")
    await message("<reply@frank>", "frank@example.com", folder="sent", in_reply_to=ref, to="ana@example.com",
                  date=NOV_2 + timedelta(hours=1))
    # From another address (her phone), so only the thread links it to the owner's reply.
    await message("<answer@ana>", "ana.phone@example.net", in_reply_to="<reply@frank>", date=NOV_2 + timedelta(days=2))
    job = await job_over(original, "follow_up")

    await defer(job.id)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await wake_due(OWNER, registry, now=DUE + timedelta(minutes=1))

    assert await state(job) == ("done", None)
    assert [m["Message-ID"] for m in mailbox.messages("Archive")] == [ref]


async def test_newer_mail_from_the_correspondent_counts_as_an_answer(test_db, mailbox: Mailbox):
    """Not every client threads its reply: a later message from the same person counts."""
    ref = mailbox.deliver(sender="ana@example.com", subject="Contract", body="Please sign")
    mailbox.create_folder("Archive")
    original = await message(ref, "ana@example.com")
    await message("<later@ana>", "Ana@Example.com", date=NOV_2 + timedelta(days=3))
    job = await job_over(original, "follow_up")

    await defer(job.id)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await wake_due(OWNER, registry, now=DUE + timedelta(minutes=1))

    assert (await state(job))[0] == "done"


async def test_defer_needs_a_date_and_a_snooze_or_follow_up_job(test_db):
    undated = await job_over(await message("<a@x>", "a@example.com"), "snooze", due=None)
    reply = await job_over(await message("<b@x>", "b@example.com"), "reply")

    with pytest.raises(ValueError, match="needs a date"):
        await defer(undated.id)
    with pytest.raises(ValueError, match="only snooze and follow-up"):
        await defer(reply.id)
    await defer(undated.id, until=DUE)
    with pytest.raises(JobNotOpen):
        await defer(undated.id, until=DUE)


async def test_the_engine_wakes_due_jobs_every_pass(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    job = await job_over(await message("<m@x>", "ana@example.com"), "snooze", due=datetime.now(UTC) - timedelta(minutes=1))
    await Job.find(Job.id == job.id).update({"$set": {"state": "snoozed"}})
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    assert (await state(job))[0] == "open"


async def test_an_answer_arriving_after_the_reminder_resolves_it(test_db, mailbox: Mailbox):
    """Also covers a reminder raised on stale mail (a sync that failed that pass): the next pass re-checks."""
    ref = mailbox.deliver(sender="ana@example.com", subject="Contract", body="Please sign")
    mailbox.create_folder("Archive")
    job = await job_over(await message(ref, "ana@example.com"), "follow_up")
    await defer(job.id)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await wake_due(OWNER, registry, now=DUE + timedelta(minutes=1))
        reminded = await state(job)
        await message("<late@ana>", "ana@example.com", date=DUE + timedelta(hours=2))
        await wake_due(OWNER, registry, now=DUE + timedelta(hours=3))

    assert reminded == ("open", "No answer from ana@example.com to “Contract” since 2026-11-02")
    assert (await state(job))[0] == "done"


async def test_a_reminder_survives_its_mail_being_archived_elsewhere(test_db, mailbox: Mailbox):
    """The owner often archives after replying; the follow-up is about the answer, not the inbox."""
    ref = mailbox.deliver(sender="ana@example.com", subject="Contract", body="Please sign")
    job = await job_over(await message(ref, "ana@example.com"), "follow_up")
    await defer(job.id)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))
    mailbox.move(ref, "Archive")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await close_handled_elsewhere(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert (await state(job))[0] == "open"


async def test_one_broken_job_doesnt_stop_the_others_waking(test_db):
    broken = Job(owner_id=OWNER, verb="follow_up", title="t", artifacts=Artifacts(), due=DUE, message_ids=[PydanticObjectId()], state="snoozed")
    await broken.insert()
    snooze = await job_over(await message("<m@x>", "ana@example.com"), "snooze")
    await defer(snooze.id)

    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert (await state(snooze))[0] == "open"


async def test_a_date_without_a_timezone_is_taken_as_utc(test_db):
    job = await job_over(await message("<m@x>", "ana@example.com"), "snooze", due=None)

    await defer(job.id, until=datetime(2026, 11, 9, 9))
    await wake_due(OWNER, PluginRegistry(), now=DUE - timedelta(minutes=1))
    early = await state(job)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert early[0] == "snoozed" and (await state(job))[0] == "open"


async def test_an_answer_to_an_earlier_reply_doesnt_resolve_a_later_one(test_db):
    """Reply, answer, reply again: the follow-up is about the last reply."""
    original = await message("<m@x>", "ana@example.com")
    await message("<reply1@frank>", "frank@example.com", folder="sent", in_reply_to="<m@x>", date=NOV_2 + timedelta(hours=1))
    await message("<answer1@ana>", "ana.phone@example.net", in_reply_to="<reply1@frank>", date=NOV_2 + timedelta(days=1))
    await message("<reply2@frank>", "frank@example.com", folder="sent", in_reply_to="<m@x>", date=NOV_2 + timedelta(days=2))
    job = await job_over(original, "follow_up")

    await defer(job.id)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert await state(job) == ("open", "No answer from ana@example.com to “Contract” since 2026-11-04")


async def test_the_owners_latest_turn_in_a_back_and_forth_is_the_one_awaiting_an_answer(test_db):
    """original → reply → answer → reply to that answer (threaded to the answer, not the original)."""
    original = await message("<m@x>", "ana@example.com")
    await message("<reply1@frank>", "frank@example.com", folder="sent", in_reply_to="<m@x>", to="ana@example.com", date=NOV_2 + timedelta(hours=1))
    await message("<answer1@ana>", "ana@example.com", in_reply_to="<reply1@frank>", date=NOV_2 + timedelta(days=1))
    await message("<reply2@frank>", "frank@example.com", folder="sent", in_reply_to="<answer1@ana>", to="Ana@Example.com", date=NOV_2 + timedelta(days=2))
    job = await job_over(original, "follow_up")

    await defer(job.id)
    await wake_due(OWNER, PluginRegistry(), now=DUE + timedelta(minutes=1))

    assert await state(job) == ("open", "No answer from ana@example.com to “Contract” since 2026-11-04")


async def test_follow_ups_wait_for_a_pass_whose_sent_folders_synced(test_db, mailbox: Mailbox):
    """A fresh test mailbox has no Sent folder, so sent sync fails: outgoing history may be stale, so a
    follow-up isn't judged this pass (a snooze still wakes)."""
    await add_owner(test_db)
    past = datetime.now(UTC) - timedelta(minutes=1)
    follow_up = await job_over(await message("<f@x>", "ana@example.com"), "follow_up", due=past)
    snooze = await job_over(await message("<s@x>", "bob@example.com"), "snooze", due=past)
    await Job.find(In(Job.id, [follow_up.id, snooze.id])).update({"$set": {"state": "snoozed"}})
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()
        waiting, snooze_woke = await state(follow_up), await state(snooze)
        mailbox.create_folder("Sent")
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    assert waiting == ("snoozed", None) and snooze_woke == ("open", None)
    assert await state(follow_up) == ("open", "No answer from ana@example.com to “Contract” since 2026-11-02")


async def test_follow_ups_wait_while_a_configured_account_is_down(test_db, mailbox: Mailbox):
    """Its sent folder can't be read, so the owner's latest reply may be missing."""
    await add_owner(test_db)
    mailbox.create_folder("Sent")
    follow_up = await job_over(await message("<f@x>", "ana@example.com"), "follow_up", due=datetime.now(UTC) - timedelta(minutes=1))
    await Job.find(Job.id == follow_up.id).update({"$set": {"state": "snoozed"}})
    down = PluginConfig(id="down", transport=StdioTransport(type="stdio", command="/nonexistent/plugin", args=[], env_from={}))
    registry = PluginRegistry()
    await registry.connect_all([reference_imap_plugin(mailbox), down])
    try:
        assert registry.states["down"].status != "connected"
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()
    finally:
        await registry.close()

    assert await state(follow_up) == ("snoozed", None)


async def test_a_reminder_the_owner_turned_into_another_action_isnt_closed_as_answered(test_db, mailbox: Mailbox):
    """wake() read a follow-up; the owner chose a reply for it meanwhile (#74). An answer then mustn't finish the reply."""
    ref = mailbox.deliver(sender="ana@example.com", subject="Contract", body="Please sign")
    job = await job_over(await message(ref, "ana@example.com"), "follow_up")
    await job.set({"reminder": "No answer from ana@example.com"})
    await message("<answer@ana>", "ana@example.com", date=DUE)
    stale = await Job.get(job.id)
    await job.set({"verb": "reply", "reminder": None, "artifacts.draft": "Signed, thanks."})
    assert stale is not None

    async with connected(reference_imap_plugin(mailbox)) as registry:
        with pytest.raises(JobNotOpen):
            await wake(stale, registry)

    assert await state(job) == ("open", None) and len(mailbox.messages("INBOX")) == 1
