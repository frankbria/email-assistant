# Unsubscribe (spec §4: never_auto, "links in email are untrusted", #90): the List-Unsubscribe target is shown to
# the owner and acted on only on their tap; a mailto goes out through the owner's mailbox to exactly its one address,
# an https link is opened by the owner's browser, never by the server. Real MongoDB; GreenMail + the reference IMAP
# plugin. The AC half (no unsubscribe without a tap, whatever the permissions) is in tests/test_permissions.py.
from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId

from app import executor
from app.executor import JobNotOpen, execute
from app.models.action_log import ActionLogEntry
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.plugins.registry import PluginRegistry
from app.unsubscribe import unsubscribe_mail
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_routes.test_jobs_api import archived, job_from
from tests.test_sync.test_inbox_sync import PLUGIN, connected
from tests.utils.auth import OWNER_ID
from tests.utils.mail_server import Mailbox, build_message, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def unsubscribe_job(mailbox: Mailbox, list_unsubscribe: str) -> Job:
    """A proposed unsubscribe over real list mail in the owner's inbox carrying `list_unsubscribe`."""
    ref = mailbox.append(
        "INBOX",
        sender="deals@shop.example",
        subject="Running shoes",
        body="30% off all running shoes",
        headers={"List-Unsubscribe": list_unsubscribe},
    )
    message = Message.model_validate(
        {
            "owner_id": OWNER_ID,
            "plugin_id": PLUGIN,
            "ref": ref,
            "message_id": ref,
            "sender": {"email": "deals@shop.example"},
            "to": [{"email": mailbox.address}],
            "cc": [],
            "date": datetime.now(UTC),
            "subject": "Running shoes",
            "snippet": "",
        }
    )
    await message.insert()
    assert message.id is not None
    job = Job(
        owner_id=OWNER_ID,
        verb="unsubscribe",
        title="Leave Shop deals",
        evidence=["30% off all running shoes"],
        artifacts=Artifacts(noise_rationale="Bulk promotions"),
        message_ids=[message.id],
    )
    await job.insert()
    return job


async def still_open(job: Job) -> bool:
    stored = await Job.get(job.id)
    return stored is not None and (stored.state, stored.sent_at) == ("open", None)


async def test_a_mailto_target_is_shown_then_sent_to_exactly_that_address_on_the_owners_tap(async_client, test_db, mailbox, plugins):
    leave = new_mailbox()
    target = f"mailto:{leave.address}?subject=unsubscribe%20deals"
    job = await unsubscribe_job(mailbox, f"<{target}>")

    shown = await async_client.get(f"/api/v1/jobs/{job.id}/unsubscribe")
    approved = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={"unsubscribe_target": shown.json()["target"]})

    assert shown.json() == {"target": target}
    assert (approved.json()["state"], approved.json()["permission_level"]) == ("done", "never_auto")
    [sent] = leave.messages("INBOX")
    assert (sent["To"], sent["Cc"], sent["Subject"]) == (leave.address, None, "unsubscribe deals")
    assert archived(mailbox)
    logged = await ActionLogEntry.find(ActionLogEntry.job_id == job.id).sort("created_at").to_list()
    assert [(entry.action, entry.by, entry.permission_level) for entry in logged] == [
        ("sent", "owner", "never_auto"),
        ("archived", "owner", "never_auto"),
    ]


async def test_an_https_target_is_returned_for_the_owners_browser_and_the_tap_finishes_the_job(async_client, test_db, mailbox, plugins):
    """The server only hands the link over; it never requests it (see test_unsubscribe.py for the structural check)."""
    leave = new_mailbox()
    job = await unsubscribe_job(mailbox, f"<mailto:{leave.address}>, <https://shop.example/u?id=7>")

    shown = await async_client.get(f"/api/v1/jobs/{job.id}/unsubscribe")
    approved = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={"unsubscribe_target": shown.json()["target"]})

    assert shown.json() == {"target": "https://shop.example/u?id=7"}  # https is preferred over mailto
    assert (approved.json()["state"], approved.json()["permission_level"]) == ("done", "never_auto")
    assert archived(mailbox) and leave.messages("INBOX") == [] and approved.json()["sent_at"] is None


@pytest.mark.parametrize("confirmed", [None, "mailto:someone@else.example", "https://shop.example/u?id=7"])
async def test_an_approval_acts_only_on_the_target_the_mail_names(async_client, test_db, mailbox, plugins, confirmed):
    leave = new_mailbox()
    job = await unsubscribe_job(mailbox, f"<mailto:{leave.address}>")

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={"unsubscribe_target": confirmed})

    assert response.status_code == 422 and "confirm the unsubscribe target" in response.json()["detail"]
    assert await still_open(job) and leave.messages("INBOX") == [] and len(mailbox.messages("INBOX")) == 1


@pytest.mark.parametrize(
    "header",
    [
        "<mailto:{leave}?subject=hi%0D%0ABcc:%20{victim}>",
        "<mailto:{leave}%0D%0ABcc:{victim}>",
        "<mailto:{leave},{victim}>",
        "<mailto:{leave}?cc={victim}>",
        "<mailto:{leave}?bcc={victim}>",
    ],
)
async def test_a_mailto_that_injects_headers_or_adds_recipients_is_never_offered_or_sent(async_client, test_db, mailbox, plugins, header):
    leave, victim = new_mailbox(), new_mailbox()
    value = header.format(leave=leave.address, victim=victim.address)
    job = await unsubscribe_job(mailbox, value)

    shown = await async_client.get(f"/api/v1/jobs/{job.id}/unsubscribe")
    approved = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={"unsubscribe_target": value.strip("<>")})

    assert shown.status_code == approved.status_code == 422
    assert "names no safe way to unsubscribe" in shown.json()["detail"]
    assert await still_open(job) and leave.messages("INBOX") == [] and victim.messages("INBOX") == []


async def test_only_an_unsubscribe_job_has_a_target(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "todo")

    response = await async_client.get(f"/api/v1/jobs/{job.id}/unsubscribe")

    assert response.status_code == 422 and "isn't an unsubscribe" in response.json()["detail"]


async def test_an_unsubscribe_request_never_sends_a_job_that_became_a_reply_meanwhile(test_db, mailbox, plugins):
    """The approval read the target, then another request turned the job into a reply: the unsubscribe tap must not
    send that reply's draft."""
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="A draft the owner never approved"))
    request = unsubscribe_mail("mailto:leave@list.example?subject=unsubscribe")
    assert request is not None

    with pytest.raises(ValueError):
        await execute(job.id, plugins, by="owner", level="never_auto", unsubscribe_request=request)

    assert ana.messages("INBOX") == [] and (await Job.get(job.id)).state == "open"


async def test_an_unsubscribe_request_never_goes_out_through_another_copy_than_the_one_read(test_db, mailbox, plugins):
    """The target was read from one copy, then a sync dropped that copy from the job: sending through the copy left
    would mail another account's unsubscribe from the wrong mailbox."""
    leave = new_mailbox()
    job = await unsubscribe_job(mailbox, f"<mailto:{leave.address}>")
    read_copy = job.message_ids[0]
    other = await unsubscribe_job(mailbox, f"<mailto:{leave.address}>")
    await Job.get_pymongo_collection().update_one({"_id": job.id}, {"$set": {"message_ids": other.message_ids}})

    with pytest.raises(JobNotOpen):
        await execute(
            job.id,
            plugins,
            by="owner",
            level="never_auto",
            unsubscribe_request=unsubscribe_mail(f"mailto:{leave.address}"),
            unsubscribe_copies=[read_copy],
        )

    assert leave.messages("INBOX") == [] and await still_open(job)


async def test_an_https_tap_never_finishes_a_job_whose_copies_changed_while_its_target_was_read(test_db, mailbox, plugins, monkeypatch):
    """The owner opened the link from the copy read; a sync swapping that copy out meanwhile leaves another account's
    copy, still subscribed: the tap must not finish the job and archive that one."""
    job = await unsubscribe_job(mailbox, "<https://shop.example/u?id=7>")
    other = await unsubscribe_job(mailbox, "<https://shop.example/u?id=8>")
    read_target = executor.unsubscribe_target_of

    async def read_then_sync_swaps_the_copy(job_id: PydanticObjectId, registry: PluginRegistry) -> str:
        target = await read_target(job_id, registry)
        await Job.get_pymongo_collection().update_one({"_id": job.id}, {"$set": {"message_ids": other.message_ids}})
        return target

    monkeypatch.setattr(executor, "unsubscribe_target_of", read_then_sync_swaps_the_copy)

    with pytest.raises(JobNotOpen):
        await executor.unsubscribe(job.id, plugins, "https://shop.example/u?id=7", level="never_auto")

    assert (await Job.get(job.id)).state == "open" and not archived(mailbox)


HOME, WORK = "home-imap", "work-imap"


async def unsubscribe_job_in_both(home: Mailbox, work: Mailbox, list_unsubscribe: str, work_list_unsubscribe: str | None = None) -> Job:
    """One list mail in both accounts with one Message-ID (#176); `work_list_unsubscribe`: the work copy names its own."""
    mail = build_message(sender="deals@shop.example", to=f"{home.address}, {work.address}", subject="Running shoes", body="30% off")
    copies = []
    for plugin_id, mailbox, header in ((HOME, home, list_unsubscribe), (WORK, work, work_list_unsubscribe or list_unsubscribe)):
        del mail["List-Unsubscribe"]
        mail["List-Unsubscribe"] = header
        with mailbox.imap() as connection:
            assert connection.append("INBOX", None, None, mail.as_bytes())[0] == "OK"
        mailbox.create_folder("Archive")
        copy = Message.model_validate(
            {
                "owner_id": OWNER_ID,
                "plugin_id": plugin_id,
                "ref": mail["Message-ID"],
                "message_id": mail["Message-ID"],
                "sender": {"email": "deals@shop.example"},
                "to": [{"email": home.address}, {"email": work.address}],
                "cc": [],
                "date": datetime.now(UTC),
                "subject": "Running shoes",
                "snippet": "",
            }
        )
        await copy.insert()
        copies.append(copy.id)
    job = Job(
        owner_id=OWNER_ID,
        verb="unsubscribe",
        title="Leave Shop deals",
        evidence=["30% off"],
        artifacts=Artifacts(noise_rationale="Bulk promotions"),
        message_ids=copies,
    )
    await job.insert()
    return job


def senders(mailbox: Mailbox) -> list[str]:
    return sorted(str(mail["From"]) for mail in mailbox.messages("INBOX"))


async def test_one_mail_in_two_accounts_is_unsubscribed_from_each_account_before_both_copies_are_archived(test_db):
    home, work, leave = new_mailbox(), new_mailbox(), new_mailbox()
    job = await unsubscribe_job_in_both(home, work, f"<mailto:{leave.address}?subject=unsubscribe>")

    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        target = await executor.unsubscribe_target_of(job.id, registry)
        finished = await executor.unsubscribe(job.id, registry, target, level="never_auto")

    assert senders(leave) == sorted([home.address, work.address])
    assert finished.state == "done" and archived(home) and archived(work)


async def test_a_retry_after_one_account_failed_sends_only_from_the_account_still_subscribed(test_db):
    home, work, leave = new_mailbox(), new_mailbox(), new_mailbox()
    job = await unsubscribe_job_in_both(home, work, f"<mailto:{leave.address}>")
    target = f"mailto:{leave.address}"

    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK, MAILBOX_SMTP_PORT="1")) as registry:
        failed = await executor.unsubscribe(job.id, registry, target, level="never_auto")
    archived_after_the_failure = archived(home)
    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        retried = await executor.unsubscribe(job.id, registry, target, level="never_auto")

    assert failed.state == "failed" and not archived_after_the_failure
    assert senders(leave) == sorted([home.address, work.address])  # home's request went out once, not again
    assert retried.state == "done" and archived(home) and archived(work)


async def test_a_mail_in_two_accounts_offers_its_mailto_over_its_link_so_each_account_can_leave(test_db):
    """The owner's browser opens one link for one subscriber; a mailto goes out from every account."""
    home, work, leave = new_mailbox(), new_mailbox(), new_mailbox()
    job = await unsubscribe_job_in_both(home, work, f"<https://shop.example/u?id=7>, <mailto:{leave.address}>")

    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        target = await executor.unsubscribe_target_of(job.id, registry)

    assert target == f"mailto:{leave.address}"


async def test_copies_whose_accounts_name_different_targets_are_never_unsubscribed_with_one_of_them(test_db):
    """A subscriber-specific address (or a forged copy) must not be used for another account."""
    home, work, leave, other = new_mailbox(), new_mailbox(), new_mailbox(), new_mailbox()
    job = await unsubscribe_job_in_both(home, work, f"<mailto:{leave.address}>", f"<mailto:{other.address}>")

    async with connected(reference_imap_plugin(home, HOME), reference_imap_plugin(work, WORK)) as registry:
        with pytest.raises(ValueError, match="different ways to unsubscribe"):
            await executor.unsubscribe(job.id, registry, f"mailto:{leave.address}", level="never_auto")

    assert leave.messages("INBOX") == other.messages("INBOX") == [] and await still_open(job)
