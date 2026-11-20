# The same mail in two accounts (spec §5.3): one job references both copies, and finishing it
# archives the mail in every account where it's still in the inbox. Two GreenMail accounts as two
# reference IMAP plugins; real MongoDB; the AI is the repo's FakeAIProvider.
import smtplib
from datetime import UTC, datetime

import pytest

from app.executor import finish, unsubscribe
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.pipeline.proposal import Proposal
from app.pipeline.run import attach_copy, sibling_job
from app.sync import SyncEngine, close_handled_elsewhere
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, add_owner, connected
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import MAIL_HOST, SMTP_PORT, Mailbox, build_message, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
HOME, WORK = "home-imap", "work-imap"


def deliver_to_both(home: Mailbox, work: Mailbox, subject: str, headers: dict[str, str] | None = None) -> str:
    """One SMTP delivery to both addresses: both copies carry the same Message-ID. `headers` adds more."""
    message = build_message(
        sender="ana@example.com", to=f"{home.address}, {work.address}", subject=subject, body="Pay invoice 4471 by Friday."
    )
    for name, value in (headers or {}).items():
        message[name] = value
    with smtplib.SMTP(MAIL_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(message)
    for mailbox in (home, work):
        mailbox._wait_for(message["Message-ID"], "INBOX")
        mailbox.create_folder("Archive")
    return str(message["Message-ID"])


def todo() -> Proposal:
    return Proposal(
        needs_owner=False,
        verb="todo",
        title="Pay invoice 4471 by Friday",
        evidence=["Pay invoice 4471 by Friday."],
        due=datetime(2026, 11, 6, tzinfo=UTC),
        confidence=0.9,
    )


async def test_the_same_mail_in_two_accounts_is_one_job_archived_in_both_when_done(test_db):
    """AC: one job; on done, both are archived."""
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    message_id = deliver_to_both(home, work, "Invoice 4471")
    provider = FakeAIProvider(result=todo())
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()
        [job] = await Job.find(Job.owner_id == OWNER).to_list()
        copies = await Message.find(Message.message_id == message_id).to_list()
        finished = await finish(job.id, "done", registry, by="owner", level="ask")

    assert sorted(job.message_ids) == sorted(copy.id for copy in copies) and len(copies) == 2
    assert len(provider.prompts) == 1  # the second copy costs no AI call
    assert (finished.state, finished.error) == ("done", None)
    for mailbox in (home, work):
        assert mailbox.messages("INBOX") == [] and [m["Message-ID"] for m in mailbox.messages("Archive")] == [message_id]


async def test_a_copy_arriving_after_its_job_was_done_is_archived_at_once(test_db):
    """Both accounts were connected before (past their first pass); the work copy is synced late."""
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    provider = FakeAIProvider(result=todo())
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()  # first passes, empty
    message_id = deliver_to_both(home, work, "Invoice 4471")
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()
        [job] = await Job.find(Job.owner_id == OWNER).to_list()
        await finish(job.id, "done", registry, by="owner", level="ask")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()

    [shared] = await Job.find(Job.owner_id == OWNER).to_list()
    assert len(shared.message_ids) == 2 and (shared.state, shared.error) == ("done", None)
    assert work.messages("INBOX") == [] and [m["Message-ID"] for m in work.messages("Archive")] == [message_id]
    assert len(provider.prompts) == 1


def unsubscribe_proposal() -> FakeAIProvider:
    return FakeAIProvider(
        result=Proposal(
            needs_owner=False,
            verb="unsubscribe",
            title="Leave Ana's invoices",
            evidence=["Pay invoice 4471 by Friday."],
            noise_rationale="Bulk mail",
            confidence=0.9,
        )
    )


async def unsubscribe_job_over_home_copy(
    test_db, home: Mailbox, work: Mailbox, leave: Mailbox, provider: FakeAIProvider
) -> tuple[Job, str]:
    """List mail in both accounts, past their first passes; only home's copy is synced, into an unsubscribe job."""
    await add_owner(test_db)
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()  # first passes, empty
    message_id = deliver_to_both(home, work, "Invoice 4471", {"List-Unsubscribe": f"<mailto:{leave.address}>"})
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()
    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    return job, message_id


async def test_a_copy_arriving_after_its_unsubscribe_was_done_gets_its_own_job_so_its_account_leaves_too(test_db):
    """#176: the unsubscribe went out only from the accounts whose copies it covered; archiving a late copy on it would
    leave that copy's account subscribed with no job left to unsubscribe it."""
    home, work, leave = new_mailbox(), new_mailbox(), new_mailbox()
    provider = unsubscribe_proposal()
    job, message_id = await unsubscribe_job_over_home_copy(test_db, home, work, leave, provider)
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await unsubscribe(job.id, registry, f"mailto:{leave.address}", level="never_auto")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()

    jobs = await Job.find(Job.owner_id == OWNER).sort("created_at").to_list()
    assert [(job.verb, job.state, len(job.message_ids)) for job in jobs] == [("unsubscribe", "done", 1), ("unsubscribe", "open", 1)]
    assert [m["Message-ID"] for m in work.messages("INBOX")] == [message_id]


async def test_a_copy_arriving_while_its_unsubscribe_is_sending_waits_instead_of_riding_on_that_send(test_db):
    """The send covers only the copies it claimed; a copy attached meanwhile would be archived by its finish (#176)."""
    home, work, leave = new_mailbox(), new_mailbox(), new_mailbox()
    provider = unsubscribe_proposal()
    job, message_id = await unsubscribe_job_over_home_copy(test_db, home, work, leave, provider)
    await Job.find(Job.id == job.id).update({"$set": {"state": "sending", "sending_since": datetime.now(UTC)}})
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()

    [stored] = await Job.find(Job.owner_id == OWNER).to_list()
    [work_copy] = await Message.find(Message.plugin_id == WORK).to_list()
    assert stored.message_ids == job.message_ids and not work_copy.pipeline_done
    assert [m["Message-ID"] for m in work.messages("INBOX")] == [message_id]
    # The sync read the job open just before the send claimed it: attaching now must still leave the copy out.
    after_stale_read = await attach_copy(job, work_copy)
    assert (after_stale_read.state, after_stale_read.message_ids) == ("sending", job.message_ids)
    # Or just before its finish went done: work's account never got the request, so its copy stays out of that archive.
    await Job.find(Job.id == job.id).update({"$set": {"state": "done", "unsubscribed_from": [HOME]}})
    after_finish = await attach_copy(job, work_copy)
    assert (after_finish.state, after_finish.message_ids) == ("done", job.message_ids)


async def test_a_first_connect_copy_is_never_archived_on_another_accounts_decision(test_db):
    """Spec §5.3: every first-pass decision is `ask`. A newly connected account's copy of mail already
    finished elsewhere gets its own job needing approval instead of being archived."""
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    message_id = deliver_to_both(home, work, "Invoice 4471")
    provider = FakeAIProvider(result=todo())
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()
        [done] = await Job.find(Job.owner_id == OWNER).to_list()
        await finish(done.id, "done", registry, by="owner", level="ask")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()  # work: first connect

    jobs = await Job.find(Job.owner_id == OWNER).sort("created_at").to_list()
    assert [(job.state, job.requires_approval, len(job.message_ids)) for job in jobs] == [("done", True, 1), ("open", True, 1)]
    assert [m["Message-ID"] for m in work.messages("INBOX")] == [message_id]


async def test_a_first_connect_copy_joining_an_open_job_makes_it_need_approval(test_db):
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await SyncEngine(
            registry, test_db["user"], poll_seconds=60, ai_provider_for=FakeAIProvider(result=todo())
        ).sync_all()  # home: past first pass
    deliver_to_both(home, work, "Invoice 4471")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=FakeAIProvider(result=todo())).sync_all()

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, len(job.message_ids), job.requires_approval) == ("open", 2, True)


async def test_mail_without_a_message_id_never_shares_a_job(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    for ref in ("<a@x>", "<b@x>"):
        message = Message.model_validate(
            {
                "owner_id": OWNER,
                "plugin_id": "proton",
                "ref": ref,
                "message_id": "",
                "sender": {"email": "a@example.com"},
                "to": [],
                "cc": [],
                "date": "2026-11-02T12:00:00Z",
                "subject": "No id",
                "snippet": "",
            }
        )
        await message.insert()
    first = await Message.find_one(Message.ref == "<a@x>")
    assert first is not None and first.id is not None
    await Job(owner_id=OWNER, verb="todo", title="t", artifacts=Artifacts(), message_ids=[first.id]).insert()

    second = await Message.find_one(Message.ref == "<b@x>")
    assert second is not None and await sibling_job(second) is None


async def test_a_copy_handled_elsewhere_doesnt_absorb_a_new_copy(test_db):
    """The owner dealt with it outside the app in one account; a copy still in another inbox needs its own job."""
    copies = []
    for plugin_id in (HOME, WORK):
        copy = Message.model_validate(
            {
                "owner_id": OWNER,
                "plugin_id": plugin_id,
                "ref": "<same@x>",
                "message_id": "<same@x>",
                "sender": {"email": "a@example.com"},
                "to": [],
                "cc": [],
                "date": "2026-11-02T12:00:00Z",
                "subject": "s",
                "snippet": "",
            }
        )
        await copy.insert()
        copies.append(copy)
    assert copies[0].id is not None
    await Job(owner_id=OWNER, verb="todo", title="t", artifacts=Artifacts(), message_ids=[copies[0].id], state="handled_elsewhere").insert()

    assert await sibling_job(copies[1]) is None


async def test_one_copy_handled_elsewhere_keeps_the_job_open_for_the_other(test_db):
    """Archived on a phone in one account only: the copy still in the other inbox keeps its job."""
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    message_id = deliver_to_both(home, work, "Invoice 4471")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=FakeAIProvider(result=todo())).sync_all()
        work_copy = await Message.find_one(Message.plugin_id == WORK)
        home.move(message_id, "Archive")
        await close_handled_elsewhere(OWNER, HOME, registry.clients[HOME])
        [after_home] = await Job.find(Job.owner_id == OWNER).to_list()
        work.move(message_id, "Archive")
        await close_handled_elsewhere(OWNER, WORK, registry.clients[WORK])
        [after_both] = await Job.find(Job.owner_id == OWNER).to_list()

    assert work_copy is not None
    assert (after_home.state, after_home.message_ids) == ("open", [work_copy.id])
    assert after_both.state == "handled_elsewhere"


async def test_a_copy_attached_to_a_finished_job_is_archived_even_after_a_crash(test_db):
    """Attached, then crashed before archiving: the next pass archives the copy."""
    await add_owner(test_db)
    home, work = new_mailbox(), new_mailbox()
    message_id = deliver_to_both(home, work, "Invoice 4471")
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=FakeAIProvider(result=todo())).sync_all()
        [job] = await Job.find(Job.owner_id == OWNER).to_list()
        await Job.find(Job.id == job.id).update({"$set": {"state": "done"}})  # finished, but the work copy wasn't archived
        await Message.find(Message.plugin_id == WORK).update({"$set": {"pipeline_done": False}})
        await SyncEngine(registry, test_db["user"], poll_seconds=60, ai_provider_for=FakeAIProvider(result=todo())).sync_all()

    assert work.messages("INBOX") == [] and [m["Message-ID"] for m in work.messages("Archive")] == [message_id]


async def test_a_new_copy_joins_the_unfinished_job_over_finished_ones(test_db):
    """E.g. home's job is done and work's first-connect copy has its own open job: a third copy joins work's."""
    copies = []
    for plugin_id in (HOME, WORK, "third-imap"):
        copy = Message.model_validate(
            {
                "owner_id": OWNER,
                "plugin_id": plugin_id,
                "ref": "<same@x>",
                "message_id": "<same@x>",
                "sender": {"email": "a@example.com"},
                "to": [],
                "cc": [],
                "date": "2026-11-02T12:00:00Z",
                "subject": "s",
                "snippet": "",
            }
        )
        await copy.insert()
        copies.append(copy)
    home_copy, work_copy, third_copy = copies
    assert home_copy.id is not None and work_copy.id is not None
    await Job(owner_id=OWNER, verb="todo", title="t", artifacts=Artifacts(), message_ids=[home_copy.id], state="done").insert()
    open_job = Job(owner_id=OWNER, verb="todo", title="t", artifacts=Artifacts(), message_ids=[work_copy.id])
    await open_job.insert()

    chosen = await sibling_job(third_copy)

    assert chosen is not None and chosen.id == open_job.id
