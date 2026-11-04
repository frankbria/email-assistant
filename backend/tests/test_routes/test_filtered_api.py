# The Filtered view (spec §10.5, AC-K.2): everything archived as noise in the last 30 days, restored through the
# History undo. Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider; real SyncEngine passes.
from datetime import UTC, datetime, timedelta

import pytest

from app.models.action_log import ActionLogEntry
from app.models.job import Artifacts
from app.permissions import PermissionSettings
from tests.test_routes.test_digest_api import seen
from tests.test_routes.test_corrections_api import DEALS, SHOP, newest_job, sync_pass
from tests.test_routes.test_jobs_api import archived, job_from
from tests.test_routes.test_restore_learning_api import NOISE
from tests.test_sync.test_inbox_sync import add_owner
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def filtered(async_client) -> list[dict[str, object]]:
    response = await async_client.get("/api/v1/filtered")
    assert response.status_code == 200
    return response.json()


async def test_ac_k_2_noise_archived_on_its_own_is_listed_in_filtered_and_restore_returns_it(async_client, test_db, mailbox, plugins):
    """AC-K.2 (Filtered half). Restoring it is the History undo, so the stream asks first from now on (#85)."""
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")  # the owner's voice is read from it
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    ai = FakeAIProvider(NOISE)
    await sync_pass(test_db, plugins, ai)  # first connect, so later mail isn't first-connect mail that always asks (§5.3)
    mailbox.deliver(sender=SHOP, subject="Weekly deals", body=DEALS.format(percent=20))
    await sync_pass(test_db, plugins, ai)
    assert archived(mailbox)

    [card] = await filtered(async_client)

    assert (card["subject"], card["sender"]["email"], card["rationale"], card["restorable"]) == ("Weekly deals", SHOP, "A promotional mailing", True)
    assert (card["entry"]["by"], card["entry"]["permission_level"]) == ("app", "autonomous")

    restored = await async_client.post(f"/api/v1/history/{card['entry']['_id']}/undo")

    assert restored.status_code == 200 and restored.json()["ok"]
    assert len(mailbox.messages("INBOX")) == 1 and mailbox.messages("Archive") == []
    [card] = await filtered(async_client)
    assert card["restorable"] is False
    mailbox.deliver(sender=SHOP, subject="Weekly deals #2", body=DEALS.format(percent=30))
    await sync_pass(test_db, plugins, ai)
    waiting = await newest_job()
    assert (waiting.verb, waiting.state, waiting.requires_approval) == ("archive_noise", "open", True)


async def test_noise_archived_more_than_30_days_ago_is_not_listed(async_client, test_db, mailbox, plugins):
    recent = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    old = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="an old newsletter"))
    for job in (old, recent):
        await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    await ActionLogEntry.find(ActionLogEntry.job_id == old.id).update({"$set": {"created_at": datetime.now(UTC) - timedelta(days=31)}})

    assert [card["entry"]["job_id"] for card in await filtered(async_client)] == [str(recent.id)]


async def test_only_noise_archives_are_listed(async_client, test_db, mailbox, plugins):
    """A finished todo or digest also archives its mail, but neither was handled as noise."""
    noise = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    todo = await job_from(new_mailbox(), mailbox, "todo", Artifacts(link="https://pay.example"))
    digest = await job_from(new_mailbox(), mailbox, "digest", Artifacts(digest="Two newsletters"))
    dismissed_noise = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a mailing"))
    for job in (noise, todo, digest):
        approved = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json=seen(job) if job is digest else {})
        assert approved.json()["state"] == "done"
    await async_client.post(f"/api/v1/jobs/{dismissed_noise.id}/dismiss")

    assert [card["entry"]["job_id"] for card in await filtered(async_client)] == [str(noise.id)]


async def test_newest_first(async_client, test_db, mailbox, plugins):
    older = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    newer = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a mailing"))
    for job in (older, newer):
        await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert [card["entry"]["job_id"] for card in await filtered(async_client)] == [str(newer.id), str(older.id)]


async def test_another_owners_noise_is_not_listed(async_client, test_db, mailbox, plugins):
    theirs = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"), owner_id="someone-else")
    await ActionLogEntry(owner_id="someone-else", action="archived", job_id=theirs.id, message_ids=theirs.message_ids,
                         by="app", permission_level="autonomous", ok=True, undoable=True).insert()

    assert await filtered(async_client) == []


async def test_a_noise_archive_that_failed_is_not_listed(async_client, test_db, mailbox, plugins):
    """Its mail never left the inbox, so there is nothing to restore."""
    failed = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    await ActionLogEntry(owner_id=OWNER_ID, action="archived", job_id=failed.id, message_ids=failed.message_ids,
                         by="app", permission_level="autonomous", ok=False, error="the server was down", undoable=False).insert()

    assert await filtered(async_client) == []


async def test_the_archived_copies_of_a_partly_failed_noise_job_are_listed(async_client, test_db, mailbox, plugins):
    """One account's copy moved, the other's failed: the moved one can still be restored."""
    partly = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))
    await ActionLogEntry(owner_id=OWNER_ID, action="archived", job_id=partly.id, message_ids=partly.message_ids,
                         by="app", permission_level="autonomous", ok=False, error="the other account was down", undoable=True).insert()

    assert [card["entry"]["job_id"] for card in await filtered(async_client)] == [str(partly.id)]
