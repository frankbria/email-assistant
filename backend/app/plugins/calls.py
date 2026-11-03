"""Calling a plugin's tools with a timeout, turning failures into errors that say which plugin,
which tool and why."""

import asyncio
from itertools import batched

from mcp import Client
from mcp.types import CallToolResult

from app.plugins.registry import result_text
from mailbox_contract import ErrorCode, InboxContainsOutput, ToolError

PLUGIN_CALL_TIMEOUT_SECONDS = 60  # one hung plugin must not stop every other plugin's sync
INBOX_CONTAINS_BATCH = 500  # the contract's cap on refs per call


class SyncError(Exception):
    """A plugin call failed; the message says which plugin, which tool and why."""


class InvalidCursor(Exception):
    """The plugin no longer accepts the stored cursor (e.g. the folder was rebuilt)."""


async def call_plugin(plugin_id: str, client: Client, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    async with asyncio.timeout(PLUGIN_CALL_TIMEOUT_SECONDS):
        result = await client.call_tool(tool, arguments)
    if result.is_error or result.structured_content is None:
        raise tool_failure(plugin_id, tool, result)
    return result.structured_content


def tool_failure(plugin_id: str, tool: str, result: CallToolResult) -> InvalidCursor | SyncError:
    if result.structured_content is None:
        return SyncError(f"{plugin_id}: {tool} failed: {result_text(result) or 'no structured result'}")
    error = ToolError.model_validate(result.structured_content)
    if error.code == ErrorCode.INVALID_CURSOR:
        return InvalidCursor(error.message)
    return SyncError(f"{plugin_id}: {tool} failed: {error.message}")


async def refs_in_inbox(plugin_id: str, client: Client, refs: list[str]) -> set[str]:
    """Which of these refs are still in the plugin's inbox."""
    present: set[str] = set()
    for batch in batched(refs, INBOX_CONTAINS_BATCH):
        answer = InboxContainsOutput.model_validate(await call_plugin(plugin_id, client, "inbox_contains", {"refs": list(batch)})).root
        if answer.keys() != set(batch):  # the contract's exact-keys rule
            raise SyncError(f"{plugin_id}: inbox_contains answered for other refs than it was asked about")
        present |= {ref for ref, in_inbox in answer.items() if in_inbox}
    return present
