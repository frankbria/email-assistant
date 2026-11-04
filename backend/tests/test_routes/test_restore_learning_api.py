# Restoring a message the app archived on its own is a "this isn't noise" correction (spec §10.4, AC-2.4): the
# stream's noise rule is forgotten and its mail asks the owner first from now on. Undoing the owner's own archive
# is only an undo. Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider; real SyncEngine passes.
import logging

import pytest

from app.models.job import Artifacts
from app.models.rule import Rule
from app.permissions import PermissionSettings
from app.pipeline.proposal import Proposal
from app.pipeline.run import act_if_autonomous
from tests.test_routes.test_corrections_api import DEALS, SHOP, newest_job, sync_pass
from tests.test_routes.test_history_api import history
from tests.test_routes.test_jobs_api import archived, job_from
from tests.test_sync.test_inbox_sync import add_owner
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
