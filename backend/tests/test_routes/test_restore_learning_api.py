# Restoring a message the app archived on its own is a "this isn't noise" correction (spec §10.4, AC-2.4): the
# stream's noise rule is forgotten and its mail asks the owner first from now on. Undoing the owner's own archive
# is only an undo. Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider; real SyncEngine passes.
import logging

import pytest

from app.api.routers.jobs import plugin_registry
from app.main import app
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.models.rule import Rule
from app.permissions import PermissionSettings
from app.pipeline.proposal import Proposal
from app.pipeline.run import act_if_autonomous, attach_copy
from tests.test_routes.test_corrections_api import DEALS, SHOP, newest_job, sync_pass
from tests.test_routes.test_history_api import history
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_pipeline.test_shared_message import HOME, WORK, deliver_to_both
from tests.test_routes.test_jobs_api import archived, job_from
from tests.test_sync.test_inbox_sync import add_owner, connected
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
NOISE = Proposal(needs_owner=False, verb="archive_noise", title="The shop's weekly garden tools deals",
                 evidence=["garden tools"], noise_rationale="A promotional mailing", confidence=0.9)


async def rules() -> list[tuple[str, str, str | None, bool]]:
    return [(rule.match, rule.value, rule.verb, rule.ask_first) for rule in await Rule.find(Rule.owner_id == OWNER_ID).to_list()]


@pytest.mark.parametrize("noise_rule", [False, True], ids=["the AI judged it noise", "a noise rule decided"])
async def test_ac_2_4_restoring_mail_the_app_archived_makes_the_next_similar_message_wait_for_the_owner(
    async_client, test_db, mailbox, plugins, noise_rule
):
    """AC-2.4. The AI still takes the next deal for noise, but it is no longer archived without the owner's tap."""
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")  # the owner's voice is read from it
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    if noise_rule:
        await Rule(owner_id=OWNER_ID, match="sender", value=SHOP, verb="archive_noise").insert()
    ai = FakeAIProvider(NOISE)
    await sync_pass(test_db, plugins, ai)  # first connect, so later mail isn't first-connect mail that always asks (§5.3)
    mailbox.deliver(sender=SHOP, subject="Weekly deals", body=DEALS.format(percent=20))
    await sync_pass(test_db, plugins, ai)
    assert archived(mailbox)
    [app_archive] = await history(async_client)
    assert (app_archive["by"], app_archive["permission_level"]) == ("app", "autonomous")

    undone = await async_client.post(f"/api/v1/history/{app_archive['_id']}/undo")

    assert undone.status_code == 200 and undone.json()["ok"]
    assert len(mailbox.messages("INBOX")) == 1 and mailbox.messages("Archive") == []
    assert await rules() == [("sender", SHOP, None, True)]
    mailbox.deliver(sender=SHOP, subject="Weekly deals #2", body=DEALS.format(percent=30))
    await sync_pass(test_db, plugins, ai)
    waiting = await newest_job()
    assert (waiting.verb, waiting.state, waiting.requires_approval) == ("archive_noise", "open", True)
    assert len(mailbox.messages("INBOX")) == 2 and mailbox.messages("Archive") == []


async def test_the_list_whose_noise_rule_decided_is_the_one_that_asks_first(async_client, test_db, mailbox, plugins):
    """The list's noise rule archived it, so the list asks first from now on, not the sender's rule that didn't decide."""
    ana = new_mailbox()
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    await Rule(owner_id=OWNER_ID, match="list_id", value="<deals.shop.example>", verb="archive_noise").insert()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb="reply").insert()
    job = await job_from(ana, mailbox, "archive_noise", Artifacts(noise_rationale="a mailing list"))
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "Deals <deals.shop.example>"}})
    await act_if_autonomous(job, plugins)
    [app_archive] = await history(async_client)

    await async_client.post(f"/api/v1/history/{app_archive['_id']}/undo")

    assert sorted(await rules()) == [("list_id", "deals.shop.example", None, True), ("sender", ana.address.lower(), "reply", False)]


async def test_a_late_copy_of_restored_mail_waits_for_the_owner_instead_of_being_archived(async_client, test_db):
    """The same mail reaching another account after the restore follows the restore, not the archive it undid."""
    await add_owner(test_db, OWNER_ID)
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    home, work = new_mailbox(), new_mailbox()
    for account in (home, work):
        account.create_folder("Sent")  # the owner's voice is read from it
    ai = FakeAIProvider(NOISE.model_copy(update={"evidence": ["invoice 4471"]}))  # the words deliver_to_both sends
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await sync_pass(test_db, registry, ai)  # first passes, empty
    message_id = deliver_to_both(home, work, "Weekly deals")
    async with connected(reference_imap_plugin(home, HOME)) as registry:
        await sync_pass(test_db, registry, ai)
        [app_archive] = await history(async_client)
        app.dependency_overrides[plugin_registry] = lambda: registry
        try:
            undone = await async_client.post(f"/api/v1/history/{app_archive['_id']}/undo")
        finally:
            app.dependency_overrides.pop(plugin_registry)
    assert undone.json()["ok"] and [m["Message-ID"] for m in home.messages("INBOX")] == [message_id]

    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        await sync_pass(test_db, registry, ai)

    assert [m["Message-ID"] for m in work.messages("INBOX")] == [message_id] and work.messages("Archive") == []
    waiting = await Job.find(Job.owner_id == OWNER_ID, Job.state == "open").to_list()
    assert [(job.verb, job.requires_approval) for job in waiting] == [("archive_noise", True)]


async def test_undoing_the_owners_own_archive_teaches_nothing(async_client, test_db, mailbox, plugins):
    """The owner archived it, so restoring it changes their own mind, not the app's judgment."""
    job = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    [owner_archive] = await history(async_client)

    undone = await async_client.post(f"/api/v1/history/{owner_archive['_id']}/undo")

    assert undone.status_code == 200 and undone.json()["ok"]
    assert await rules() == []


async def test_a_lesson_that_fails_to_store_still_returns_the_restore(async_client, test_db, mailbox, plugins, caplog):
    ana = new_mailbox()
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    job = await job_from(ana, mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    await act_if_autonomous(job, plugins)
    [app_archive] = await history(async_client)
    # A stored rule for the sender that can't be read: learning from the restore fails, as a broken collection does.
    await Rule.get_pymongo_collection().insert_one({"owner_id": OWNER_ID, "match": "sender", "value": ana.address.lower(), "verb": "not a verb"})

    with caplog.at_level(logging.ERROR, logger="app.api.routers.history"):
        undone = await async_client.post(f"/api/v1/history/{app_archive['_id']}/undo")

    assert undone.status_code == 200 and undone.json()["ok"]
    assert len(mailbox.messages("INBOX")) == 1
    assert "Couldn't learn from the restore" in caplog.text


async def test_marking_the_stream_noise_again_lets_its_mail_be_archived_without_asking(async_client, test_db, mailbox, plugins):
    """The owner's later "this is noise" outranks the restore that came before it."""
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, ask_first=True).insert()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Yes"))

    await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})

    assert await rules() == [("sender", ana.address.lower(), "archive_noise", False)]


async def test_a_copy_joining_an_unfinished_job_brings_its_streams_ask_first_with_it(test_db, mailbox):
    """An open job a copy joins (e.g. one an archive failed on, reopened) must not act on its own once the
    copy's stream asks first."""
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "archive_noise")
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address.lower(), ask_first=True).insert()
    copy = await Message.get(job.message_ids[0])
    assert copy is not None and not copy.first_pass

    joined = await attach_copy(job, copy)

    assert joined.requires_approval


async def test_a_must_ask_copy_already_attached_to_a_finished_job_gets_its_own_job(test_db, mailbox, plugins):
    """A copy can end up on a finished job: its sibling finished while it attached, or a crash came between
    attaching and processing. If its stream asks first, it still isn't archived without the owner's tap."""
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")
    ana = new_mailbox()
    copy_job = await job_from(ana, mailbox, "archive_noise")
    [copy_id] = copy_job.message_ids
    await copy_job.delete()
    archived_elsewhere = await job_from(new_mailbox(), mailbox, "archive_noise", state="done", permission_level="autonomous")
    await Message.find(Message.id == archived_elsewhere.message_ids[0]).update({"$set": {"pipeline_done": True}})
    await Job.find(Job.id == archived_elsewhere.id).update({"$push": {"message_ids": copy_id}})
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address.lower(), ask_first=True).insert()

    await sync_pass(test_db, plugins, FakeAIProvider(NOISE))

    copy_subject = (await Message.get(copy_id)).subject
    assert copy_subject in [str(mail["Subject"]) for mail in mailbox.messages("INBOX")]
    waiting = await newest_job()
    assert waiting.message_ids == [copy_id] and (waiting.state, waiting.requires_approval) == ("open", True)
    assert copy_id not in (await Job.get(archived_elsewhere.id)).message_ids


async def test_a_pending_job_from_before_the_lesson_waits_once_its_stream_asks_first(test_db, mailbox, plugins):
    """A job stored before the owner's restore (e.g. a crash came before acting) is recovered later: the rule
    learned meanwhile still holds it for the owner, whatever its stored requires_approval says."""
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    ana = new_mailbox()
    pending = await job_from(ana, mailbox, "archive_noise", Artifacts(noise_rationale="A promotional mailing"))
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address.lower(), ask_first=True).insert()

    await act_if_autonomous(pending, plugins)

    assert len(mailbox.messages("INBOX")) == 1 and mailbox.messages("Archive") == []
    assert (await Job.get(pending.id)).state == "open"
