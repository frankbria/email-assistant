"""Sync (spec §5.2, §5.3): poll each plugin's inbox and sent folders from their stored cursors, poll
at once when a `push` plugin says new mail arrived, and close jobs whose message left the inbox
outside the app."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from datetime import UTC, datetime, timedelta
from typing import Literal

from beanie.operators import In
from mcp import Client
from pymongo.asynchronous.collection import AsyncCollection

from app.models.job import Job
from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from app.models.user_settings import UserSettings
from app.executor import wake_due
from app.permissions import sync_permissions_file
from app.pipeline.run import process_pending
from app.plugins.calls import InvalidCursor, SyncError, call_plugin, refs_in_inbox
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import AIProvider
from mailbox_contract import INBOX_URI, Capability, ListMessagesOutput

logger = logging.getLogger(__name__)

Folder = Literal["inbox", "sent"]

PAGE_SIZE = 100
FIRST_CONNECT_DAYS = 14


async def list_folder(
    plugin_id: str, client: Client, folder: Folder, cursor: str | None, since: datetime, page_size: int
) -> ListMessagesOutput:
    """One page of the folder after `cursor`; without a cursor, from `since`."""
    arguments: dict[str, object] = {"folder": folder, "cursor": cursor, "since": since.isoformat(), "limit": page_size}
    return ListMessagesOutput.model_validate(await call_plugin(plugin_id, client, "list_messages", arguments))


async def store_if_new(message: Message) -> bool:
    """Dedupe within one account by ref and by Message-ID (one delivery can land twice).
    A blank Message-ID (the header is missing) identifies nothing, so only the ref counts then."""
    same_mail: list[dict[str, str]] = [{"ref": message.ref}]
    if message.message_id:
        same_mail.append({"message_id": message.message_id})
    duplicate = await Message.find_one(
        Message.owner_id == message.owner_id, Message.plugin_id == message.plugin_id, {"$or": same_mail}
    )
    if duplicate is not None:
        return False
    await message.insert()
    return True


async def folder_cursor(owner_id: str, plugin_id: str, folder: Folder) -> SyncCursor:
    stored = await SyncCursor.find_one(
        SyncCursor.owner_id == owner_id, SyncCursor.plugin_id == plugin_id, SyncCursor.folder == folder
    )
    return stored or SyncCursor(owner_id=owner_id, plugin_id=plugin_id, folder=folder, first_pass_complete=False)


async def store_page(
    owner_id: str, plugin_id: str, page: ListMessagesOutput, first_pass: bool = False, folder: Folder = "inbox"
) -> list[Message]:
    """The page's messages that weren't stored yet, now stored.
    shortcut: refs are unique per account, so self-addressed mail is stored once, under the folder synced
    first; store per folder if follow_up (#69) or voice samples need both copies."""
    stored = []
    for summary in page.messages:
        message = Message(owner_id=owner_id, plugin_id=plugin_id, folder=folder, first_pass=first_pass, **summary.model_dump())
        if await store_if_new(message):
            stored.append(message)
    return stored


async def sync_folder(
    owner_id: str,
    plugin_id: str,
    client: Client,
    folder: Folder = "inbox",
    page_size: int = PAGE_SIZE,
    window_days: int = FIRST_CONNECT_DAYS,
) -> list[Message]:
    """Store the folder's mail that arrived since its stored cursor and return it, oldest first.
    Without a cursor only the last `window_days` are listed; older mail is left alone. Inbox mail
    stored before the first listing completes is marked `first_pass` (spec §5.3).

    The cursor is saved after each page is stored: a crash in between re-lists that page,
    and dedupe drops what was already stored, so nothing is missed or duplicated."""
    cursor = await folder_cursor(owner_id, plugin_id, folder)
    since = datetime.now(UTC) - timedelta(days=window_days)
    new_messages: list[Message] = []
    while True:
        try:
            page = await list_folder(plugin_id, client, folder, cursor.cursor, since, page_size)
        except InvalidCursor as error:
            if cursor.cursor is None:
                raise SyncError(f"{plugin_id}: list_messages rejected a fresh start: {error}") from error
            logger.warning("Plugin %s no longer accepts its %s cursor (%s); listing from the start", plugin_id, folder, error)
            cursor.cursor = None
            continue
        first_pass = folder == "inbox" and not cursor.first_pass_complete
        new_messages += await store_page(owner_id, plugin_id, page, first_pass, folder)
        cursor.cursor = page.next_cursor
        cursor.first_pass_complete = cursor.first_pass_complete or not page.has_more
        cursor.updated_at = datetime.now(UTC)
        await cursor.save()
        if not page.has_more:
            return new_messages


async def close_handled_elsewhere(owner_id: str, plugin_id: str, client: Client) -> int:
    """Close the open jobs over this plugin's messages that left the inbox outside the app
    (archived on a phone, moved by a filter), so the app never archives them again; a job shared with
    a copy in another inbox just lets go of the gone copy. Returns how many closed."""
    # A job reopened with an error (a finish that failed partway) stays for the owner to retry.
    # A follow-up waits for an answer, not for its mail to stay in the inbox (owners archive after replying).
    open_jobs = await Job.find(Job.owner_id == owner_id, Job.state == "open", {"error": None}, Job.verb != "follow_up").to_list()
    referenced = list({message_id for job in open_jobs for message_id in job.message_ids})
    messages = await Message.find(In(Message.id, referenced), Message.plugin_id == plugin_id).to_list()
    present = await refs_in_inbox(plugin_id, client, [message.ref for message in messages])
    gone = {message.id for message in messages if message.ref not in present}
    closed = 0
    for job in [job for job in open_jobs if gone.intersection(job.message_ids)]:
        # Still open and still error-free: an owner action or a failed finish that landed meanwhile wins.
        unchanged = Job.find(Job.id == job.id, Job.state == "open", {"error": None})
        if all(message_id in gone for message_id in job.message_ids):
            closed += (await unchanged.update({"$set": {"state": "handled_elsewhere"}})).modified_count
        else:  # a copy still waits in another inbox (spec §5.3): the job stays open for it
            await unchanged.update({"$pull": {"message_ids": {"$in": list(gone)}}})
    return closed


class SyncEngine:
    """Polls every connected plugin each interval; a push from any plugin, or a settings change, starts a pass early.
    `poll_seconds` and `first_connect_days` apply until the owner saves their own on the settings screen."""

    def __init__(
        self,
        plugins: PluginRegistry,
        users: AsyncCollection[dict[str, object]],
        poll_seconds: float,
        first_connect_days: int = FIRST_CONNECT_DAYS,
        ai_provider_for: Callable[[str], Awaitable[AIProvider]] | None = None,
        ai_monthly_cap: int | None = None,
        permissions_file: Path | None = None,
    ) -> None:
        self.plugins = plugins
        self.users = users
        self.poll_seconds = poll_seconds
        self.first_connect_days = first_connect_days
        self.ai_provider_for = ai_provider_for  # the owner's provider; None: sync only, no jobs (e.g. tests of sync alone)
        self.ai_monthly_cap = ai_monthly_cap
        self.permissions_file = permissions_file  # None: the stored settings alone (e.g. tests of sync alone)
        self.wake = asyncio.Event()
        self._listeners: dict[str, tuple[Client, asyncio.Task[None]]] = {}

    async def run(self) -> None:
        try:
            while True:
                self.wake.clear()
                self._listen_for_push()
                poll_seconds = self.poll_seconds
                try:
                    poll_seconds = await self.sync_all()
                except Exception:  # e.g. MongoDB briefly unreachable: the next pass retries
                    logger.exception("Sync pass failed; retrying next pass")
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(poll_seconds):
                        await self.wake.wait()
        finally:
            await self._stop_listeners()

    async def sync_all(self) -> float:
        """One pass; returns the seconds to the next, read from the owner's settings each pass so a change applies
        without a restart."""
        # Better Auth's `user` collection holds exactly one document: the owner.
        owner = await self.users.find_one({}, {"_id": 1})
        if owner is None:
            return self.poll_seconds  # nobody has signed up yet, so there is no one to sync for
        owner_id = str(owner["_id"])
        # Mail sync must not depend on reading settings: on a failure use the defaults, and leave mail pending.
        try:
            saved = await UserSettings.find_one(UserSettings.user_id == owner_id)
        except Exception:
            logger.exception("Reading the owner's settings failed; using the defaults this pass")
            saved = None
        window_days = saved.first_connect_days if saved else self.first_connect_days
        try:
            provider = await self.ai_provider_for(owner_id) if self.ai_provider_for is not None else None
        except Exception:
            logger.exception("Choosing the AI provider failed; new mail stays pending until the next pass")
            provider = None
        if self.permissions_file is not None:
            try:  # before the pipeline, so an edited permissions.yaml applies to this pass's mail
                await sync_permissions_file(owner_id, self.permissions_file)
            except Exception:
                logger.exception("Syncing permissions.yaml failed; retrying next pass")
        sent_synced = [await self._sync_plugin(owner_id, plugin_id, client, window_days, provider) for plugin_id, client in list(self.plugins.clients.items())]
        # Outgoing history is current only if every enabled account is connected and its sent folder synced.
        accounts_up = all(state.status in ("connected", "disabled") for state in self.plugins.states.values())
        try:  # snoozes and follow-ups whose date has come; follow-ups only with current outgoing history
            await wake_due(owner_id, self.plugins, datetime.now(UTC), check_follow_ups=accounts_up and all(sent_synced))
        except Exception:
            logger.exception("Waking due jobs failed; retrying next pass")
        return saved.poll_seconds if saved else self.poll_seconds

    async def _sync_plugin(
        self, owner_id: str, plugin_id: str, client: Client, window_days: int, provider: AIProvider | None
    ) -> bool:
        """Inbox, then sent, then the pipeline: each separately, so one failing never holds up the others."""
        try:
            new_messages = await sync_folder(owner_id, plugin_id, client, window_days=window_days)
            handled_elsewhere = await close_handled_elsewhere(owner_id, plugin_id, client)
        except Exception:
            logger.exception("Sync of plugin %s failed; retrying next pass", plugin_id)
            return False
        if new_messages:
            logger.info("Plugin %s: %d new messages", plugin_id, len(new_messages))
        if handled_elsewhere:
            logger.info("Plugin %s: %d jobs handled elsewhere", plugin_id, handled_elsewhere)
        sent_synced = True
        try:  # before the pipeline, so proposals see the owner's latest voice and forwards
            await sync_folder(owner_id, plugin_id, client, folder="sent", window_days=window_days)
        except Exception:
            logger.exception("Sync of plugin %s's sent folder failed; retrying next pass", plugin_id)
            sent_synced = False
        if provider is not None:
            try:
                await process_pending(owner_id, plugin_id, client, provider, self.ai_monthly_cap, self.plugins)
            except Exception:  # pending mail stays pending: the next pass picks it up
                logger.exception("Pipeline for plugin %s failed; retrying next pass", plugin_id)
        return sent_synced

    def _listen_for_push(self) -> None:
        """(Re)subscribe to every connected `push` plugin; a reconnect brings a new client."""
        for plugin_id, client in self.plugins.clients.items():
            if self._pushes(plugin_id) and not self._listening(plugin_id, client):
                self._listeners[plugin_id] = (client, asyncio.create_task(self._listen(plugin_id, client)))

    def _pushes(self, plugin_id: str) -> bool:
        info = self.plugins.states[plugin_id].info
        return info is not None and Capability.PUSH in info.capabilities

    def _listening(self, plugin_id: str, client: Client) -> bool:
        listening = self._listeners.get(plugin_id)
        return listening is not None and listening[0] is client and not listening[1].done()

    async def _listen(self, plugin_id: str, client: Client) -> None:
        try:
            async with client.listen(resource_subscriptions=[INBOX_URI]) as subscription:
                async for _ in subscription:
                    self.wake.set()
        except Exception:
            logger.exception("Push subscription to plugin %s ended; resubscribing next pass", plugin_id)

    async def _stop_listeners(self) -> None:
        listeners = [listener for _, listener in self._listeners.values()]
        for listener in listeners:
            listener.cancel()
        await asyncio.gather(*listeners, return_exceptions=True)
