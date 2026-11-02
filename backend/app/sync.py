"""New-mail detection (spec §5.3): poll each plugin's inbox from its stored cursor, and poll at
once when a `push` plugin says new mail arrived."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from mcp import Client
from mcp.types import CallToolResult
from pymongo.asynchronous.collection import AsyncCollection

from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from app.plugins.registry import PluginRegistry, result_text
from mailbox_contract import INBOX_URI, Capability, ErrorCode, ListMessagesOutput, ToolError

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
FIRST_CONNECT_DAYS = 14
LIST_TIMEOUT_SECONDS = 60  # one hung plugin must not stop every other plugin's sync


class SyncError(Exception):
    """A plugin could not list its inbox; the message says which and why."""


class InvalidCursor(Exception):
    """The plugin no longer accepts the stored cursor (e.g. the folder was rebuilt)."""


async def list_inbox(
    plugin_id: str, client: Client, cursor: str | None, since: datetime, page_size: int
) -> ListMessagesOutput:
    """One page of the inbox after `cursor`; without a cursor, from `since`."""
    arguments = {"folder": "inbox", "cursor": cursor, "since": since.isoformat(), "limit": page_size}
    async with asyncio.timeout(LIST_TIMEOUT_SECONDS):
        result = await client.call_tool("list_messages", arguments)
    if result.is_error or result.structured_content is None:
        raise list_failure(plugin_id, result)
    return ListMessagesOutput.model_validate(result.structured_content)


def list_failure(plugin_id: str, result: CallToolResult) -> InvalidCursor | SyncError:
    if result.structured_content is None:
        return SyncError(f"{plugin_id}: list_messages failed: {result_text(result) or 'no structured result'}")
    error = ToolError.model_validate(result.structured_content)
    if error.code == ErrorCode.INVALID_CURSOR:
        return InvalidCursor(error.message)
    return SyncError(f"{plugin_id}: list_messages failed: {error.message}")


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


async def inbox_cursor(owner_id: str, plugin_id: str) -> SyncCursor:
    stored = await SyncCursor.find_one(
        SyncCursor.owner_id == owner_id, SyncCursor.plugin_id == plugin_id, SyncCursor.folder == "inbox"
    )
    return stored or SyncCursor(owner_id=owner_id, plugin_id=plugin_id, folder="inbox")


async def store_page(
    owner_id: str, plugin_id: str, page: ListMessagesOutput, first_pass: bool = False
) -> list[Message]:
    """The page's messages that weren't stored yet, now stored."""
    stored = []
    for summary in page.messages:
        message = Message(owner_id=owner_id, plugin_id=plugin_id, first_pass=first_pass, **summary.model_dump())
        if await store_if_new(message):
            stored.append(message)
    return stored


async def sync_inbox(
    owner_id: str, plugin_id: str, client: Client, page_size: int = PAGE_SIZE, window_days: int = FIRST_CONNECT_DAYS
) -> list[Message]:
    """Store the inbox mail that arrived since the stored cursor and return it, oldest first.
    Without a cursor only the last `window_days` are listed; older mail is left alone.
    Mail stored before the first listing completes is marked `first_pass` (spec §5.3).

    The cursor is saved after each page is stored: a crash in between re-lists that page,
    and dedupe drops what was already stored, so nothing is missed or duplicated."""
    cursor = await inbox_cursor(owner_id, plugin_id)
    since = datetime.now(UTC) - timedelta(days=window_days)
    new_messages: list[Message] = []
    while True:
        try:
            page = await list_inbox(plugin_id, client, cursor.cursor, since, page_size)
        except InvalidCursor as error:
            if cursor.cursor is None:
                raise SyncError(f"{plugin_id}: list_messages rejected a fresh start: {error}") from error
            logger.warning("Plugin %s no longer accepts its cursor (%s); listing the inbox from the start", plugin_id, error)
            cursor.cursor = None
            continue
        new_messages += await store_page(owner_id, plugin_id, page, first_pass=not cursor.first_pass_complete)
        cursor.cursor = page.next_cursor
        cursor.first_pass_complete = cursor.first_pass_complete or not page.has_more
        cursor.updated_at = datetime.now(UTC)
        await cursor.save()
        if not page.has_more:
            return new_messages


class SyncEngine:
    """Polls every connected plugin each interval; a push from any plugin starts a pass early."""

    def __init__(
        self,
        plugins: PluginRegistry,
        users: AsyncCollection[dict[str, object]],
        poll_seconds: float,
        first_connect_days: int = FIRST_CONNECT_DAYS,
    ) -> None:
        self.plugins = plugins
        self.users = users
        self.poll_seconds = poll_seconds
        self.first_connect_days = first_connect_days
        self.wake = asyncio.Event()
        self._listeners: dict[str, tuple[Client, asyncio.Task[None]]] = {}

    async def run(self) -> None:
        try:
            while True:
                self.wake.clear()
                self._listen_for_push()
                try:
                    await self.sync_all()
                except Exception:  # e.g. MongoDB briefly unreachable: the next pass retries
                    logger.exception("Sync pass failed; retrying next pass")
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(self.poll_seconds):
                        await self.wake.wait()
        finally:
            await self._stop_listeners()

    async def sync_all(self) -> None:
        # Better Auth's `user` collection holds exactly one document: the owner.
        owner = await self.users.find_one({}, {"_id": 1})
        if owner is None:
            return  # nobody has signed up yet, so there is no one to sync for
        for plugin_id, client in list(self.plugins.clients.items()):
            try:
                new_messages = await sync_inbox(
                    str(owner["_id"]), plugin_id, client, window_days=self.first_connect_days
                )
            except Exception:
                logger.exception("Sync of plugin %s failed; retrying next pass", plugin_id)
                continue
            if new_messages:
                logger.info("Plugin %s: %d new messages", plugin_id, len(new_messages))

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
