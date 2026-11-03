# Sent-folder sync (spec §5.2): the owner's sent mail is stored for voice, forward history and
# follow_up, never handed to the pipeline. Reference IMAP plugin on GreenMail, real MongoDB.
import logging
from datetime import UTC, datetime, timedelta

import pytest

from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from app.models.message import recent_sent
from app.sync import SyncEngine, sync_folder
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, PLUGIN, add_owner, connected
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


async def stored(folder: str) -> list[str]:
    return [m.message_id for m in await Message.find(Message.owner_id == OWNER, Message.folder == folder).to_list()]


async def test_sent_mail_is_stored_as_sent_and_never_handed_to_the_pipeline(test_db, mailbox: Mailbox):
    """AC1, through the engine's pass and through each folder's hand-off."""
    await add_owner(test_db)
    arrived = mailbox.deliver(sender="ana@example.com", subject="Lunch?", body="x")
    replied = mailbox.append("Sent", sender=mailbox.address, to="ana@example.com", subject="Re: Lunch?", body="Sure!")
    mailbox.append("Sent", sender=mailbox.address, to="old@example.com", subject="Old", body="x",
                   received=datetime.now(UTC) - timedelta(days=30))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()
        later = mailbox.append("Sent", sender=mailbox.address, to="ben@example.com", subject="Hello", body="x")
        inbox_handoff = await sync_folder(OWNER, PLUGIN, registry.clients[PLUGIN])
        sent_handoff = await sync_folder(OWNER, PLUGIN, registry.clients[PLUGIN], folder="sent")

    assert await stored("inbox") == [arrived]
    assert sorted(await stored("sent")) == sorted([replied, later])  # the 30-day-old one is outside the window
    assert inbox_handoff == [] and [m.message_id for m in sent_handoff] == [later]
    assert all(not m.first_pass for m in await Message.find(Message.folder == "sent").to_list())


async def test_a_failing_sent_folder_does_not_stop_inbox_sync(test_db, mailbox: Mailbox, caplog):
    """AC2: a fresh test mailbox has no Sent folder, so listing it fails; the inbox still syncs and
    its new mail is still handed on (once lost, stored mail is never offered again)."""
    await add_owner(test_db)
    arrived = mailbox.deliver(sender="ana@example.com", subject="Hi", body="x")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        with caplog.at_level(logging.INFO, logger="app.sync"):
            await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    messages = [record.getMessage() for record in caplog.records]
    assert f"Plugin {PLUGIN}: 1 new messages" in messages
    assert f"Sync of plugin {PLUGIN}'s sent folder failed; retrying next pass" in messages

    assert await stored("inbox") == [arrived]
    cursors = {c.folder: c.cursor for c in await SyncCursor.find(SyncCursor.owner_id == OWNER).to_list()}
    assert cursors.keys() == {"inbox"} and cursors["inbox"]


async def test_recent_sent_is_newest_first_per_correspondent_and_owner(test_db):
    def sent(owner_id: str, to: str, days_ago: int, ref: str) -> Message:
        return Message.model_validate({
            "owner_id": owner_id, "plugin_id": PLUGIN, "folder": "sent", "ref": ref, "message_id": f"<{ref}@x>",
            "sender": {"email": "owner@example.com"}, "to": [{"email": to}], "cc": [],
            "date": datetime.now(UTC) - timedelta(days=days_ago), "subject": ref, "snippet": "",
        })

    for message in (sent(OWNER, "ana@example.com", 3, "a-old"), sent(OWNER, "Ana@Example.com", 1, "a-new"),
                    sent(OWNER, "ben@example.com", 2, "b"), sent("someone-else", "ana@example.com", 0, "other")):
        await message.insert()
    await Message.model_validate({**sent(OWNER, "ana@example.com", 0, "inbox-copy").model_dump(exclude={"id"}), "folder": "inbox"}).insert()

    assert [m.ref for m in await recent_sent(OWNER, limit=2)] == ["a-new", "b"]
    assert [m.ref for m in await recent_sent(OWNER, limit=5, to="ANA@example.com")] == ["a-new", "a-old"]
