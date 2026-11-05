"""The MCP server exposing ImapMailbox as the mailbox/1 tools.

Every tool returns a CallToolResult: success carries the contract model as structured
content, failure carries a mailbox/1 ToolError with isError set.
"""

import json
import logging
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

import anyio
import anyio.from_thread
import anyio.lowlevel
from mailbox_contract import INBOX_URI, RETRYABLE_CODES, Address, Capability, ErrorCode, ToolError
from mcp.server.mcpserver import MCPServer
from mcp.server.subscriptions import InMemorySubscriptionBus, ResourceUpdated
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from imap_mailbox.settings import ImapMailboxSettings

logger = logging.getLogger(__name__)

# Servers drop an IDLE after 30 minutes (RFC 2177; Gmail at about 29), so renew sooner.
IDLE_SECONDS = 25 * 60
RETRY_SECONDS = 30


def respond(produce: Callable[[], BaseModel]) -> CallToolResult:
    try:
        result = produce()
    except MailboxError as error:
        failure = ToolError(code=error.code, message=error.message, retryable=error.code in RETRYABLE_CODES)
        return CallToolResult(
            content=[TextContent(type="text", text=failure.message)],
            structured_content=failure.model_dump(mode="json"),
            is_error=True,
        )
    except Exception as error:  # report, don't crash the server
        failure = ToolError(code=ErrorCode.INTERNAL, message=f"Plugin error: {error}", retryable=True)
        return CallToolResult(
            content=[TextContent(type="text", text=failure.message)],
            structured_content=failure.model_dump(mode="json"),
            is_error=True,
        )
    payload = result.model_dump(mode="json", by_alias=True)
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))], structured_content=payload)


def watch_inbox(mailbox: ImapMailbox, publish: Callable[[], None], stopped: threading.Event) -> None:
    """IMAP IDLE on the inbox, publishing every arrival. Failures only delay mail until the next poll."""
    while not stopped.is_set():
        try:
            if mailbox.wait_for_new_mail(IDLE_SECONDS) and not stopped.is_set():
                publish()
        except Exception:
            logger.exception("Watching the inbox over IDLE failed; retrying in %s s", RETRY_SECONDS)
            stopped.wait(RETRY_SECONDS)


def build_server(mailbox: ImapMailbox, name: str = "imap-mailbox") -> MCPServer:
    capabilities = mailbox.mailbox_info().capabilities
    bus = InMemorySubscriptionBus()

    @asynccontextmanager
    async def push_new_mail(_: MCPServer) -> AsyncIterator[None]:
        """Watch the inbox while the server runs (`push`). A daemon thread, because a blocking IDLE
        must not keep a stopping plugin alive."""
        token = anyio.lowlevel.current_token()
        stopped = threading.Event()

        def publish() -> None:
            anyio.from_thread.run(bus.publish, ResourceUpdated(uri=INBOX_URI), token=token)

        threading.Thread(target=watch_inbox, args=(mailbox, publish, stopped), daemon=True).start()
        try:
            yield
        finally:
            stopped.set()

    server = MCPServer(name, subscriptions=bus, lifespan=push_new_mail if Capability.PUSH in capabilities else None)

    @server.tool()
    def mailbox_info() -> CallToolResult:
        return respond(mailbox.mailbox_info)

    @server.tool()
    def health() -> CallToolResult:
        return respond(mailbox.health)

    @server.tool()
    def list_messages(
        folder: Literal["inbox", "sent"],
        cursor: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> CallToolResult:
        return respond(lambda: mailbox.list_messages(folder, cursor, since, max(1, min(limit, 500))))

    @server.tool()
    def inbox_contains(refs: list[str]) -> CallToolResult:
        return respond(lambda: mailbox.inbox_contains(refs))

    @server.tool()
    def get_message(ref: str) -> CallToolResult:
        return respond(lambda: mailbox.get_message(ref))

    @server.tool()
    def archive(ref: str) -> CallToolResult:
        return respond(lambda: mailbox.archive(ref))

    @server.tool()
    def restore(ref: str) -> CallToolResult:
        return respond(lambda: mailbox.restore(ref))

    @server.tool()
    def send(
        to: list[Address],
        subject: str,
        body_text: str,
        cc: list[Address] | None = None,
        in_reply_to_ref: str | None = None,
    ) -> CallToolResult:
        return respond(lambda: mailbox.send(to, cc or [], subject, body_text, in_reply_to_ref))

    if Capability.REPAIR in capabilities:

        @server.tool()
        def repair(action: str) -> CallToolResult:
            return respond(lambda: mailbox.repair(action))

    return server


def main() -> None:
    settings = ImapMailboxSettings()
    server = build_server(ImapMailbox(settings), name=settings.plugin_name)
    if sys.argv[1:2] == ["http"]:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run()


if __name__ == "__main__":
    main()
