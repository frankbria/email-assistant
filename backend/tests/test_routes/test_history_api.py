# The action log and undo behind the History timeline (spec §9, §10.6): every action, by the app or the owner,
# with undo where possible (restore after an archive; a send can't be unsent). Real MongoDB; GreenMail + the
# reference IMAP plugin.
from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId

from app.api.routers.jobs import plugin_registry
from app.main import app
from app.models.action_log import ActionLogEntry
from app.models.job import Artifacts
from app.permissions import PermissionSettings
from app.pipeline.run import act_if_autonomous
from app.plugins.registry import PluginRegistry
from tests.test_routes.test_jobs_api import archived, job_from
from tests.utils.auth import OWNER_ID
from tests.utils.mail_server import new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def history(async_client) -> list[dict[str, object]]:
    response = await async_client.get("/api/v1/history")
    assert response.status_code == 200
    return [card["entry"] for card in response.json()]


async def test_archive_then_undo_returns_the_message_to_the_inbox_and_logs_both(async_client, test_db, mailbox, plugins):
    """AC: Archive then undo returns the message to the inbox on the test server and logs both entries."""
    job = await job_from(new_mailbox(), mailbox, "todo", Artifacts(link="https://pay.example"))
    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    assert archived(mailbox)
    [archive_entry] = await history(async_client)

    undone = await async_client.post(f"/api/v1/history/{archive_entry['_id']}/undo")

    assert undone.status_code == 200
    assert len(mailbox.messages("INBOX")) == 1 and mailbox.messages("Archive") == []
    restore_entry, archive_entry = await history(async_client)
    assert undone.json()["_id"] == restore_entry["_id"]
    assert (archive_entry["action"], archive_entry["by"], archive_entry["permission_level"]) == ("archived", "owner", "ask")
    assert (archive_entry["ok"], archive_entry["undoable"], archive_entry["undone"]) == (True, True, True)
    assert (restore_entry["action"], restore_entry["by"], restore_entry["ok"], restore_entry["undoable"]) == ("restored", "owner", True, False)
    assert restore_entry["job_id"] == str(job.id) and restore_entry["message_ids"] == archive_entry["message_ids"] == [str(job.message_ids[0])]


async def test_a_sent_reply_cant_be_unsent_but_its_archive_can_be_undone(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Thursday works."))
    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    archive_entry, sent_entry = await history(async_client)

    refused = await async_client.post(f"/api/v1/history/{sent_entry['_id']}/undo")

    assert (sent_entry["action"], sent_entry["ok"], sent_entry["undoable"]) == ("sent", True, False)
    assert (archive_entry["action"], archive_entry["undoable"]) == ("archived", True)
    assert refused.status_code == 409 and refused.json()["detail"] == "a sent email can't be unsent"


async def test_an_entry_is_undone_once(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "todo", Artifacts(link="https://pay.example"))
    await async_client.post(f"/api/v1/jobs/{job.id}/dismiss")
    [dismissed] = await history(async_client)

    first = await async_client.post(f"/api/v1/history/{dismissed['_id']}/undo")
    second = await async_client.post(f"/api/v1/history/{dismissed['_id']}/undo")

    assert (dismissed["action"], dismissed["permission_level"], dismissed["undoable"]) == ("dismissed", None, True)
    assert first.status_code == 200 and second.status_code == 409 and second.json()["detail"] == "it was already undone"
    assert [entry["action"] for entry in await history(async_client)] == ["restored", "dismissed"]


async def test_a_failed_restore_is_logged_and_the_archive_stays_undoable(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "todo", Artifacts(link="https://pay.example"))
    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    [archive_entry] = await history(async_client)
    app.dependency_overrides[plugin_registry] = lambda: PluginRegistry()  # the plugin went away

    failed = await async_client.post(f"/api/v1/history/{archive_entry['_id']}/undo")

    assert failed.status_code == 200
    assert (failed.json()["action"], failed.json()["ok"]) == ("restored", False)
    assert failed.json()["error"] == "reference-imap isn't connected, so the message is still archived"
    restore_entry, archive_entry = await history(async_client)
    assert restore_entry["_id"] == failed.json()["_id"] and archive_entry["undone"] is False
    assert archived(mailbox)


async def test_only_an_archive_can_be_undone(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "snooze", due=datetime.now(UTC) + timedelta(days=1))
    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})
    [snoozed] = await history(async_client)

    refused = await async_client.post(f"/api/v1/history/{snoozed['_id']}/undo")

    assert (snoozed["action"], snoozed["undoable"]) == ("snoozed", False)
    assert refused.status_code == 409 and refused.json()["detail"] == "only archived mail can be undone (restored to the inbox)"


async def test_another_owners_entries_are_not_listed_or_undoable(async_client, test_db, plugins):
    theirs = ActionLogEntry(owner_id="someone-else", action="archived", job_id=PydanticObjectId(), message_ids=[PydanticObjectId()],
                            by="owner", permission_level="ask", ok=True, undoable=True)
    await theirs.insert()

    assert await history(async_client) == []
    assert (await async_client.post(f"/api/v1/history/{theirs.id}/undo")).status_code == 404


async def test_an_autonomous_archive_is_logged_as_the_apps_with_its_level(async_client, test_db, mailbox, plugins):
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    job = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="a newsletter"))

    await act_if_autonomous(job, plugins)

    [entry] = await history(async_client)
    assert (entry["action"], entry["by"], entry["permission_level"], entry["undoable"]) == ("archived", "app", "autonomous", True)
    assert archived(mailbox)


async def test_a_failed_send_is_logged_with_its_reason(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "forward", Artifacts(draft="FYI"))

    await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    [entry] = await history(async_client)
    assert (entry["action"], entry["ok"], entry["error"], entry["undoable"]) == ("sent", False, "choose who to forward it to", False)
