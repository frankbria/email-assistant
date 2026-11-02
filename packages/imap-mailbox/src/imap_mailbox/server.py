"""The MCP server exposing ImapMailbox as the mailbox/1 tools.

Every tool returns a CallToolResult: success carries the contract model as structured
content, failure carries a mailbox/1 ToolError with isError set.
"""

import json
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from imap_mailbox.settings import ImapMailboxSettings
from mailbox_contract import Address, Capability, ErrorCode, RETRYABLE_CODES, ToolError


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


def build_server(mailbox: ImapMailbox, name: str = "imap-mailbox") -> MCPServer:
    server = MCPServer(name)

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

    if Capability.REPAIR in mailbox.mailbox_info().capabilities:

        @server.tool()
        def repair(action: str) -> CallToolResult:
            return respond(lambda: mailbox.repair(action))

    return server


def main() -> None:
    settings = ImapMailboxSettings()  # type: ignore[call-arg]  # required fields come from the environment
    server = build_server(ImapMailbox(settings), name=settings.plugin_name)
    if sys.argv[1:2] == ["http"]:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run()


if __name__ == "__main__":
    main()
