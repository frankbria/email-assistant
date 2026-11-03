# Per-verb permissions (spec §4 table, §9, AC-K.1–K.3): a readable permissions.yaml in sync with the
# stored settings; ceilings can't be exceeded; autonomous verbs act without a tap, `ask` waits for one.
# Real MongoDB; GreenMail + the reference IMAP plugin for the end-to-end checks; the AI is FakeAIProvider.
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.models.job import Job
from app.models.message import Message
from app.permissions import PermissionSettings, PermissionsRejected, level_for, parse_permissions, set_levels, sync_permissions_file
from app.pipeline.proposal import Proposal
from app.sync import SyncEngine
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, add_owner, connected
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox, new_mailbox


@pytest.mark.parametrize(("text", "explained"), [
    ("unsubscribe: autonomous", "unsubscribe can't be autonomous: its highest level is never_auto (links in email are untrusted)"),
    ("forward: autonomous", "forward can't be autonomous: its highest level is ask (new recipients come from AI judgment)"),
    ("todo: autonomous", "todo can't be autonomous: its highest level is ask (completing it needs the owner)"),
    ("reply: sometimes", "reply: 'sometimes' isn't a level (autonomous, ask or never_auto)"),
    ("replay: ask", "replay isn't a verb"),
    ("- reply", "permissions.yaml must map each verb to a level"),
])
def test_a_file_above_a_ceiling_or_malformed_is_rejected_with_the_reason(text: str, explained: str):
    """AC-K.3 (file half)."""
    with pytest.raises(PermissionsRejected) as rejected:
        parse_permissions(text)

    assert str(rejected.value) == explained


def test_lowering_a_level_is_always_allowed():
    assert parse_permissions("forward: never_auto\nreply: autonomous") == {"forward": "never_auto", "reply": "autonomous"}


async def test_defaults_come_from_the_table_and_unknown_verbs_ask(test_db):
    assert (await level_for(OWNER, "reply"), await level_for(OWNER, "unsubscribe")) == ("ask", "never_auto")
    assert await level_for(OWNER, "teleport") == "ask"


async def test_the_file_and_the_store_stay_in_sync(test_db, tmp_path: Path):
    path = tmp_path / "permissions.yaml"

    await sync_permissions_file(OWNER, path)  # no file yet: written from the settings
    written = yaml.safe_load(path.read_text())
    path.write_text("archive_noise: autonomous\nreply: ask\n")
    await sync_permissions_file(OWNER, path)  # the owner edited the file: the store follows
    from_file = await level_for(OWNER, "archive_noise")
    await set_levels(OWNER, {"archive_noise": "ask"}, path)  # the settings screen changed it: the file follows

    assert written["unsubscribe"] == "never_auto" and written["archive_noise"] == "ask"
    assert from_file == "autonomous"
    assert yaml.safe_load(path.read_text())["archive_noise"] == "ask" and await level_for(OWNER, "archive_noise") == "ask"


async def test_a_rejected_file_keeps_the_stored_settings_and_says_why(test_db, tmp_path: Path):
    path = tmp_path / "permissions.yaml"
    await set_levels(OWNER, {"archive_noise": "autonomous"}, path)
    path.write_text("archive_noise: ask\nunsubscribe: autonomous\n")

    await sync_permissions_file(OWNER, path)

    stored = await PermissionSettings.find_one(PermissionSettings.owner_id == OWNER)
    assert await level_for(OWNER, "archive_noise") == "autonomous"  # unchanged: the whole file was rejected
    assert stored is not None and stored.file_error == (
        "unsubscribe can't be autonomous: its highest level is never_auto (links in email are untrusted)"
    )


async def test_the_settings_screen_gets_the_same_ceilings(test_db, tmp_path: Path):
    with pytest.raises(PermissionsRejected, match="forward can't be autonomous"):
        await set_levels(OWNER, {"forward": "autonomous"}, tmp_path / "permissions.yaml")




def proposal(**changes: object) -> Proposal:
    base = Proposal(needs_owner=False, verb="archive_noise", title="Shop.example promo for running shoes",
                    evidence=["30% off all running shoes"], noise_rationale="Bulk promotion", confidence=0.9)
    return base.model_copy(update=changes)


async def pipeline_pass(test_db, mailbox: Mailbox, path: Path, result: Proposal) -> None:
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, provider=FakeAIProvider(result=result),
                         permissions_file=path).sync_all()


@pytest.mark.usefixtures("mail_server")
async def test_autonomous_noise_is_archived_without_a_tap(test_db, mailbox: Mailbox, tmp_path: Path):
    """AC-K.2 (executor half). An empty first pass first, so the mail isn't first-connect mail (always ask)."""
    await add_owner(test_db)
    mailbox.create_folder("Archive")
    path = tmp_path / "permissions.yaml"
    path.write_text("archive_noise: autonomous\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    ref = mailbox.deliver(sender="deals@shop.example", subject="Running shoes", body="This week only: 30% off all running shoes")

    await pipeline_pass(test_db, mailbox, path, proposal())

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.permission_level) == ("done", "autonomous")
    assert mailbox.messages("INBOX") == [] and [m["Message-ID"] for m in mailbox.messages("Archive")] == [ref]


@pytest.mark.usefixtures("mail_server")
async def test_a_reply_set_to_ask_is_never_sent_without_a_tap(test_db, mailbox: Mailbox, tmp_path: Path):
    """AC-K.1."""
    await add_owner(test_db)
    ana = new_mailbox()
    path = tmp_path / "permissions.yaml"
    path.write_text("reply: ask\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    ana.deliver_to(mailbox, subject="Lunch?", body="Lunch on Friday?")
    reply = proposal(verb="reply", title="Ana asks about lunch Friday", evidence=["Lunch on Friday?"], noise_rationale=None,
                     draft="Friday works!")

    await pipeline_pass(test_db, mailbox, path, reply)

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.permission_level) == ("open", None) and ana.messages("INBOX") == []


@pytest.mark.usefixtures("mail_server")
async def test_an_autonomous_reply_goes_only_to_the_sender(test_db, mailbox: Mailbox, tmp_path: Path):
    await add_owner(test_db)
    mailbox.create_folder("Archive")
    mailbox.create_folder("Sent")
    ana = new_mailbox()
    path = tmp_path / "permissions.yaml"
    path.write_text("reply: autonomous\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    ana.deliver_to(mailbox, subject="Lunch?", body="Lunch on Friday?")
    reply = proposal(verb="reply", title="Ana asks about lunch Friday", evidence=["Lunch on Friday?"], noise_rationale=None,
                     draft="Friday works!")

    await pipeline_pass(test_db, mailbox, path, reply)

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    [sent] = ana.messages("INBOX")
    assert (job.state, job.permission_level) == ("done", "autonomous") and sent["Subject"] == "Re: Lunch?"


@pytest.mark.usefixtures("mail_server")
async def test_first_connect_mail_waits_for_a_tap_even_when_autonomous(test_db, mailbox: Mailbox, tmp_path: Path):
    """Spec §5.3: every first-pass decision is `ask`."""
    await add_owner(test_db)
    mailbox.create_folder("Archive")  # archiving would work: only the first-pass rule holds it back
    mailbox.deliver(sender="deals@shop.example", subject="Running shoes", body="This week only: 30% off all running shoes")
    path = tmp_path / "permissions.yaml"
    path.write_text("archive_noise: autonomous\n")

    await pipeline_pass(test_db, mailbox, path, proposal())

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.requires_approval, job.error) == ("open", True, None) and len(mailbox.messages("INBOX")) == 1


async def test_an_edit_is_seen_even_with_the_same_modification_time(test_db, tmp_path: Path):
    path = tmp_path / "permissions.yaml"
    await set_levels(OWNER, {}, path)
    stamp = path.stat().st_mtime_ns
    path.write_text("archive_noise: autonomous\n")
    os.utime(path, ns=(stamp, stamp))  # a coarse clock, or two edits in one tick

    await sync_permissions_file(OWNER, path)

    assert await level_for(OWNER, "archive_noise") == "autonomous"


async def test_an_empty_or_truncated_file_never_resets_the_settings(test_db, tmp_path: Path):
    path = tmp_path / "permissions.yaml"
    await set_levels(OWNER, {"archive_noise": "autonomous"}, path)
    path.write_text("")

    await sync_permissions_file(OWNER, path)

    assert await level_for(OWNER, "archive_noise") == "autonomous"
    assert yaml.safe_load(path.read_text())["archive_noise"] == "autonomous"  # rewritten from the store


async def test_a_file_that_cant_be_written_still_stores_the_change_and_says_why(test_db, tmp_path: Path):
    read_only = tmp_path / "config"
    read_only.mkdir()
    read_only.chmod(0o500)
    try:
        await set_levels(OWNER, {"archive_noise": "autonomous"}, read_only / "permissions.yaml")
    finally:
        read_only.chmod(0o700)

    stored = await PermissionSettings.find_one(PermissionSettings.owner_id == OWNER)
    assert await level_for(OWNER, "archive_noise") == "autonomous"
    assert stored is not None and stored.file_error is not None and stored.file_error.startswith("couldn't write")


async def test_a_stored_level_above_its_ceiling_is_held_to_the_ceiling(test_db):
    """E.g. a ceiling lowered in a later version: the stored setting never exceeds it."""
    await PermissionSettings(owner_id=OWNER, levels={"forward": "autonomous"}).insert()

    assert await level_for(OWNER, "forward") == "ask"


@pytest.mark.usefixtures("mail_server")
async def test_list_mail_is_never_replied_to_autonomously(test_db, mailbox: Mailbox, tmp_path: Path):
    """Replying to a list posts to everyone on it: that waits for a tap whatever the setting."""
    await add_owner(test_db)
    path = tmp_path / "permissions.yaml"
    path.write_text("reply: autonomous\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    mailbox.append("INBOX", sender="team@lists.example", subject="Standup", body="Who's in?",
                   headers={"List-Id": "Team <team.lists.example>"})
    reply = proposal(verb="reply", title="Team standup check", evidence=["Who's in?"], noise_rationale=None, draft="I'm in")

    await pipeline_pass(test_db, mailbox, path, reply)

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.permission_level) == ("open", None)


@pytest.mark.usefixtures("mail_server")
async def test_a_failed_autonomous_action_isnt_recorded_as_done_autonomously(test_db, mailbox: Mailbox, tmp_path: Path):
    """No Archive folder: the archive fails and the job reopens for the owner."""
    await add_owner(test_db)
    path = tmp_path / "permissions.yaml"
    path.write_text("archive_noise: autonomous\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    mailbox.deliver(sender="deals@shop.example", subject="Running shoes", body="This week only: 30% off all running shoes")

    await pipeline_pass(test_db, mailbox, path, proposal())

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.permission_level) == ("open", None) and job.error is not None


@pytest.mark.usefixtures("mail_server")
async def test_an_autonomous_action_interrupted_by_a_crash_runs_on_the_next_pass(test_db, mailbox: Mailbox, tmp_path: Path):
    await add_owner(test_db)
    mailbox.create_folder("Archive")
    path = tmp_path / "permissions.yaml"
    path.write_text("archive_noise: ask\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    mailbox.deliver(sender="deals@shop.example", subject="Running shoes", body="This week only: 30% off all running shoes")
    await pipeline_pass(test_db, mailbox, path, proposal())  # stored the job under `ask`
    path.write_text("archive_noise: autonomous\n")
    await Message.find_all().update({"$set": {"pipeline_done": False}})  # as if it crashed before acting

    await pipeline_pass(test_db, mailbox, path, proposal())

    [job] = await Job.find(Job.owner_id == OWNER).to_list()
    assert (job.state, job.permission_level) == ("done", "autonomous") and mailbox.messages("INBOX") == []


@pytest.mark.usefixtures("mail_server")
async def test_an_autonomous_send_interrupted_by_a_crash_is_recovered_once_its_claim_is_stale(test_db, mailbox: Mailbox, tmp_path: Path):
    await add_owner(test_db)
    mailbox.create_folder("Archive")
    mailbox.create_folder("Sent")
    ana = new_mailbox()
    path = tmp_path / "permissions.yaml"
    path.write_text("reply: ask\n")
    await pipeline_pass(test_db, mailbox, path, proposal())
    ana.deliver_to(mailbox, subject="Lunch?", body="Lunch on Friday?")
    reply = proposal(verb="reply", title="Ana asks about lunch Friday", evidence=["Lunch on Friday?"], noise_rationale=None, draft="Friday works!")
    await pipeline_pass(test_db, mailbox, path, reply)
    path.write_text("reply: autonomous\n")
    await Message.find_all().update({"$set": {"pipeline_done": False}})
    await Job.find_all().update({"$set": {"state": "sending", "sending_since": datetime.now(UTC) - timedelta(minutes=1)}})

    await pipeline_pass(test_db, mailbox, path, reply)  # claim still fresh: wait
    fresh = [(job.state, m.pipeline_done) for job in await Job.find_all().to_list() for m in await Message.find(Message.folder == "inbox").to_list()]
    await Job.find_all().update({"$set": {"sending_since": datetime.now(UTC) - timedelta(minutes=30)}})
    await pipeline_pass(test_db, mailbox, path, reply)  # stale: recovered

    [job] = await Job.find_all().to_list()
    assert fresh == [("sending", False)]
    assert (job.state, job.permission_level) == ("done", "autonomous") and len(ana.messages("INBOX")) == 1
