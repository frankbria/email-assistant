# Inbox sync (spec §5.3) against real plugins: the reference IMAP plugin on GreenMail, and the
# fake plugin for push and failures. Real MongoDB; no mocks.
import asyncio
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app import sync

from app.config import Settings
from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from app.sync import SyncEngine, SyncError, store_page, sync_inbox
from mailbox_contract import ListMessagesOutput, MessageSummary
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.utils.mail_server import Mailbox

FAKE_PLUGIN = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mailbox_plugin.py"
OWNER = "owner-1"
PLUGIN = "reference-imap"

pytestmark = pytest.mark.usefixtures("mail_server")


@asynccontextmanager
async def connected(*configs: PluginConfig) -> AsyncIterator[PluginRegistry]:
    """Each use starts fresh plugin processes, like the app after a restart."""
    registry = PluginRegistry()
    await registry.connect_all(list(configs))
    try:
        for config in configs:
            assert registry.states[config.id].status == "connected", registry.states[config.id].reason
        yield registry
    finally:
        await registry.close()


def fake_plugin(plugin_id: str, env_from: dict[str, str]) -> PluginConfig:
    return PluginConfig(
        id=plugin_id,
        transport=StdioTransport(type="stdio", command=sys.executable, args=[str(FAKE_PLUGIN)], env_from=env_from),
    )


async def stored_message_ids() -> list[str]:
    return [message.message_id for message in await Message.find(Message.owner_id == OWNER).to_list()]


async def add_owner(database: AsyncDatabase[dict[str, object]], owner_id: str = OWNER) -> None:
    """The owner as Better Auth stores it: the single `user` document."""
    await database["user"].insert_one({"_id": owner_id, "role": "owner"})


async def eventually(condition: Callable[[], Awaitable[bool]], timeout_seconds: float = 15) -> None:
    async with asyncio.timeout(timeout_seconds):
        while not await condition():
            await asyncio.sleep(0.1)


async def test_catches_up_after_an_outage_with_no_duplicates_or_missed_mail(test_db, mailbox: Mailbox):
    """AC-P.3: when the plugin returns after an outage, sync resumes from the stored cursor."""
    before = mailbox.deliver(sender="a@example.com", subject="Before", body="one")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        first = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    during = [mailbox.deliver(sender="b@example.com", subject=f"During {n}", body="x") for n in range(3)]
    async with connected(reference_imap_plugin(mailbox)) as registry:
        caught_up = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN], page_size=2)
        again = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [message.message_id for message in first] == [before]
    assert [message.message_id for message in caught_up] == during
    assert again == []
    assert sorted(await stored_message_ids()) == sorted([before, *during])
    cursor = await SyncCursor.find_one(SyncCursor.owner_id == OWNER, SyncCursor.plugin_id == PLUGIN)
    assert cursor is not None and cursor.folder == "inbox" and cursor.cursor


async def test_one_mail_under_two_refs_or_listed_twice_is_stored_once(test_db):
    """Dedupe by ref and by Message-ID: refs are opaque, and one delivery can get two."""
    def summary(ref: str, message_id: str) -> MessageSummary:
        return MessageSummary.model_validate({
            "ref": ref, "message_id": message_id, "from": {"email": "a@example.com"}, "to": [], "cc": [],
            "date": "2026-11-02T12:00:00Z", "subject": "s", "snippet": "",
        })

    page = ListMessagesOutput(
        messages=[
            summary("uid-1", "<one@x>"), summary("uid-2", "<one@x>"), summary("uid-3", "<two@x>"),
            # Mail without a Message-ID header: a blank id says nothing about being the same mail.
            summary("uid-4", ""), summary("uid-5", ""),
        ],
        next_cursor="5", has_more=False,
    )
    first = await store_page(OWNER, PLUGIN, page)
    relisted = await store_page(OWNER, PLUGIN, page)

    assert [message.ref for message in first] == ["uid-1", "uid-3", "uid-4", "uid-5"]
    assert relisted == []
    assert sorted(await stored_message_ids()) == ["", "", "<one@x>", "<two@x>"]


async def test_a_cursor_the_plugin_no_longer_accepts_restarts_without_duplicates(test_db, mailbox: Mailbox):
    seen = mailbox.deliver(sender="a@example.com", subject="Seen", body="x")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])
        cursor = await SyncCursor.find_one(SyncCursor.owner_id == OWNER)
        assert cursor is not None
        cursor.cursor = "0:999"  # e.g. the folder was rebuilt and its UIDVALIDITY changed
        await cursor.save()
        unseen = mailbox.deliver(sender="a@example.com", subject="Unseen", body="x")

        new = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [message.message_id for message in new] == [unseen]
    assert sorted(await stored_message_ids()) == sorted([seen, unseen])


def days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def test_first_connect_takes_only_the_last_14_days_and_archives_nothing(test_db, mailbox: Mailbox):
    """Spec §5.3 first connect: older mail stays untouched; the first pass is all `ask`."""
    older = mailbox.append("INBOX", sender="a@example.com", subject="15 days", body="x", received=days_ago(15))
    recent = mailbox.append("INBOX", sender="a@example.com", subject="13 days", body="x", received=days_ago(13))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        first_pass = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [(message.message_id, message.first_pass) for message in first_pass] == [(recent, True)]
    assert await stored_message_ids() == [recent]
    assert sorted(message["Message-ID"] for message in mailbox.messages("INBOX")) == sorted([older, recent])


async def test_older_mail_at_a_higher_uid_than_recent_mail_never_enters(test_db, mailbox: Mailbox):
    """E.g. imported history: IMAP UID order is not date order."""
    recent = mailbox.append("INBOX", sender="a@example.com", subject="2 days", body="x", received=days_ago(2))
    mailbox.append("INBOX", sender="a@example.com", subject="30 days", body="x", received=days_ago(30))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        first_pass = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])
        next_pass = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [message.message_id for message in first_pass] == [recent]
    assert next_pass == []


async def test_the_whole_first_pass_is_marked_even_across_pages_but_later_mail_is_not(test_db, mailbox: Mailbox):
    week_old = [
        mailbox.append("INBOX", sender="a@example.com", subject=f"Week {n}", body="x", received=days_ago(7))
        for n in range(3)
    ]
    async with connected(reference_imap_plugin(mailbox)) as registry:
        first_pass = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN], page_size=1)
        later = mailbox.deliver(sender="b@example.com", subject="Later", body="x")
        afterwards = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [(message.message_id, message.first_pass) for message in first_pass] == [(m, True) for m in week_old]
    assert [(message.message_id, message.first_pass) for message in afterwards] == [(later, False)]


async def test_a_cursor_saved_before_first_pass_tracking_counts_as_past_its_first_pass(test_db, mailbox: Mailbox):
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])
        await test_db["sync_cursors"].update_many({}, {"$unset": {"first_pass_complete": ""}})
        later = mailbox.deliver(sender="b@example.com", subject="Later", body="x")

        afterwards = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [(message.message_id, message.first_pass) for message in afterwards] == [(later, False)]


async def test_the_first_connect_window_is_configurable(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    older = mailbox.append("INBOX", sender="a@example.com", subject="15 days", body="x", received=days_ago(15))
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, first_connect_days=16).sync_all()

    assert await stored_message_ids() == [older]


async def test_restarting_after_a_rejected_cursor_keeps_the_window_and_is_not_a_first_pass(test_db, mailbox: Mailbox):
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])
        cursor = await SyncCursor.find_one(SyncCursor.owner_id == OWNER)
        assert cursor is not None
        cursor.cursor = "0:999"  # e.g. the folder was rebuilt and its UIDVALIDITY changed
        await cursor.save()
        mailbox.append("INBOX", sender="a@example.com", subject="Moved back in", body="x", received=days_ago(30))
        unseen = mailbox.deliver(sender="a@example.com", subject="Unseen", body="x")

        new = await sync_inbox(OWNER, PLUGIN, registry.clients[PLUGIN])

    assert [(message.message_id, message.first_pass) for message in new] == [(unseen, False)]


async def test_a_failing_list_messages_raises_with_the_plugins_words(test_db, monkeypatch):
    monkeypatch.setenv("FAKE_FAILS", "1")
    async with connected(fake_plugin("broken", {"FAKE_LIST_FAILS": "FAKE_FAILS"})) as registry:
        with pytest.raises(SyncError, match="broken.*list_messages failed"):
            await sync_inbox(OWNER, "broken", registry.clients["broken"])


async def test_engine_polls_on_its_interval_and_one_failing_plugin_does_not_stop_the_others(
    test_db, mailbox: Mailbox, monkeypatch
):
    monkeypatch.setenv("FAKE_FAILS", "1")
    await add_owner(test_db)
    async with connected(fake_plugin("broken", {"FAKE_LIST_FAILS": "FAKE_FAILS"}), reference_imap_plugin(mailbox)) as registry:
        engine = SyncEngine(registry, test_db["user"], poll_seconds=0.2)
        running = asyncio.create_task(engine.run())
        try:
            await eventually(lambda: SyncCursor.find_one(SyncCursor.plugin_id == PLUGIN).exists())
            arrived = mailbox.deliver(sender="a@example.com", subject="New", body="x")

            await eventually(lambda: Message.find_one(Message.message_id == arrived).exists())
        finally:
            running.cancel()
            await asyncio.wait({running})


async def test_a_plugin_that_never_answers_does_not_hold_up_the_others(test_db, mailbox: Mailbox, monkeypatch):
    monkeypatch.setenv("FAKE_HANGS", "3600")
    monkeypatch.setattr(sync, "LIST_TIMEOUT_SECONDS", 0.5)
    await add_owner(test_db)
    arrived = mailbox.deliver(sender="a@example.com", subject="New", body="x")
    hung = fake_plugin("hung", {"FAKE_LIST_DELAY": "FAKE_HANGS"})
    async with connected(hung, reference_imap_plugin(mailbox)) as registry:
        async with asyncio.timeout(10):
            await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    assert await stored_message_ids() == [arrived]


async def test_a_failing_pass_is_logged_and_the_engine_keeps_polling(caplog):
    unreachable: AsyncMongoClient[dict[str, object]] = AsyncMongoClient("mongodb://127.0.0.1:9", serverSelectionTimeoutMS=50)
    engine = SyncEngine(PluginRegistry(), unreachable["nowhere"]["user"], poll_seconds=0.05)
    running = asyncio.create_task(engine.run())

    async def failed_twice() -> bool:
        return sum("Sync pass failed" in record.message for record in caplog.records) >= 2

    try:
        await eventually(failed_twice)
        assert not running.done()
    finally:
        running.cancel()
        await asyncio.wait({running})
        await unreachable.close()


async def test_engine_waits_for_an_owner_before_syncing(test_db, mailbox: Mailbox):
    mailbox.deliver(sender="a@example.com", subject="Early", body="x")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()

    assert await Message.find_all().count() == 0


async def test_push_from_a_plugin_polls_it_without_waiting_for_the_interval(test_db, monkeypatch):
    monkeypatch.setenv("FAKE_PUSH", "push")
    await add_owner(test_db)
    async with connected(fake_plugin("pushy", {"FAKE_CAPABILITIES": "FAKE_PUSH"})) as registry:
        engine = SyncEngine(registry, test_db["user"], poll_seconds=3600)
        running = asyncio.create_task(engine.run())

        async def cursor() -> str | None:
            stored = await SyncCursor.find_one(SyncCursor.plugin_id == "pushy")
            return stored.cursor if stored else None

        async def polled_again() -> bool:
            # Pushes before the subscription is acknowledged are lost, so keep pushing.
            await registry.clients["pushy"].call_tool("fake_new_mail", {})
            return await cursor() not in (None, "1")

        try:
            await eventually(lambda: SyncCursor.find_one(SyncCursor.plugin_id == "pushy").exists())
            await eventually(polled_again)
        finally:
            running.cancel()
            await asyncio.wait({running})


@pytest.mark.parametrize("variable", ["SYNC_POLL_SECONDS", "FIRST_CONNECT_DAYS"])
@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_poll_interval_or_window_that_is_not_positive_is_rejected_at_startup(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError, match=variable.lower()):
        Settings()
