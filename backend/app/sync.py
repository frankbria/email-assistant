"""New-mail detection (spec §5.3): poll each plugin's inbox from its stored cursor, and poll at
once when a `push` plugin says new mail arrived."""

import asyncio
import logging
from datetime import UTC, datetime

from mcp import Client
from mcp.types import TextContent
from pymongo.asynchronous.collection import AsyncCollection

from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from app.plugins.registry import PluginRegistry
from mailbox_contract import INBOX_URI, Capability, ErrorCode, ListMessagesOutput, ToolError

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


class SyncError(Exception):
    """A plugin could not list its inbox; the message says which and why."""


class InvalidCursor(Exception):
    """The plugin no longer accepts the stored cursor (e.g. the folder was rebuilt)."""


async def list_inbox(plugin_id: str, client: Client, cursor: str | None, page_size: int) -> ListMessagesOutput:
    """One page of the inbox after `cursor`."""
    result = await client.call_tool("list_messages", {"folder": "inbox", "cursor": cursor, "limit": page_size})
    if not result.is_error and result.structured_content is not None:
        return ListMessagesOutput.model_validate(result.structured_content)
    if result.structured_content is not None:
        error = ToolError.model_validate(result.structured_content)
        if error.code == ErrorCode.INVALID_CURSOR:
            raise InvalidCursor(error.message)
        reason = error.message
    else:
        reason = " ".join(block.text for block in result.content if isinstance(block, TextContent))
    raise SyncError(f"{plugin_id}: list_messages failed: {reason or 'no structured result'}")


async def store_if_new(message: Message) -> bool:
    """Dedupe within one account by ref and by Message-ID (one delivery can land twice)."""
    duplicate = await Message.find_one(
        Message.owner_id == message.owner_id,
        Message.plugin_id == message.plugin_id,
        {"$or": [{"ref": message.ref}, {"message_id": message.message_id}]},
    )
    if duplicate is not None:
        return False
    await message.insert()
    return True


async def sync_inbox(owner_id: str, plugin_id: str, client: Client, page_size: int = PAGE_SIZE) -> list[Message]:
    """Store the inbox mail that arrived since the stored cursor and return it, oldest first.

    The cursor is saved after each page is stored: a crash in between re-lists that page,
    and dedupe drops what was already stored, so nothing is missed or duplicated."""
    cursor = await SyncCursor.find_one(
        SyncCursor.owner_id == owner_id, SyncCursor.plugin_id == plugin_id, SyncCursor.folder == "inbox"
    ) or SyncCursor(owner_id=owner_id, plugin_id=plugin_id, folder="inbox")
    new_messages: list[Message] = []
    while True:
        try:
            page = await list_inbox(plugin_id, client, cursor.cursor, page_size)
        except InvalidCursor as error:
            if cursor.cursor is None:
                raise SyncError(f"{plugin_id}: list_messages rejected a fresh start: {error}") from error
            logger.warning("Plugin %s no longer accepts its cursor (%s); listing the inbox from the start", plugin_id, error)
            cursor.cursor = None
            continue
        for summary in page.messages:
            message = Message(owner_id=owner_id, plugin_id=plugin_id, **summary.model_dump())
            if await store_if_new(message):
                new_messages.append(message)
        cursor.cursor = page.next_cursor
        cursor.updated_at = datetime.now(UTC)
        await cursor.save()
        if not page.has_more:
            return new_messages


class SyncEngine:
    """Polls every connected plugin each interval; a push from any plugin starts a pass early."""

    def __init__(self, plugins: PluginRegistry, users: AsyncCollection[dict[str, object]], poll_seconds: float) -> None:
        self.plugins = plugins
        self.users = users
        self.poll_seconds = poll_seconds
        self.wake = asyncio.Event()
        self._listeners: dict[str, tuple[Client, asyncio.Task[None]]] = {}

    async def run(self) -> None:
        try:
            while True:
                self.wake.clear()
                self._listen_for_push()
                await self.sync_all()
                try:
                    async with asyncio.timeout(self.poll_seconds):
                        await self.wake.wait()
                except TimeoutError:
                    pass
        finally:
            listeners = [listener for _, listener in self._listeners.values()]
            for listener in listeners:
                listener.cancel()
            await asyncio.gather(*listeners, return_exceptions=True)

    async def sync_all(self) -> None:
        # Better Auth's `user` collection holds exactly one document: the owner.
        owner = await self.users.find_one({}, {"_id": 1})
        if owner is None:
            return  # nobody has signed up yet, so there is no one to sync for
        for plugin_id, client in list(self.plugins.clients.items()):
            try:
                new_messages = await sync_inbox(str(owner["_id"]), plugin_id, client)
            except Exception:
                logger.exception("Sync of plugin %s failed; retrying next pass", plugin_id)
                continue
            if new_messages:
                logger.info("Plugin %s: %d new messages", plugin_id, len(new_messages))

    def _listen_for_push(self) -> None:
        """(Re)subscribe to every connected `push` plugin; a reconnect brings a new client."""
        for plugin_id, client in self.plugins.clients.items():
            state = self.plugins.states[plugin_id]
            if state.info is None or Capability.PUSH not in state.info.capabilities:
                continue
            listening = self._listeners.get(plugin_id)
            if listening is not None and listening[0] is client and not listening[1].done():
                continue
            self._listeners[plugin_id] = (client, asyncio.create_task(self._listen(plugin_id, client)))

    async def _listen(self, plugin_id: str, client: Client) -> None:
        try:
            async with client.listen(resource_subscriptions=[INBOX_URI]) as subscription:
                async for _ in subscription:
                    self.wake.set()
        except Exception:
            logger.exception("Push subscription to plugin %s ended; resubscribing next pass", plugin_id)
