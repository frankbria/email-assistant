"""A minimal real mailbox/1 MCP server for tests (stdio by default, `http <port>` for HTTP).

FAKE_CONTRACT_VERSION, FAKE_ACCOUNT, FAKE_CAPABILITIES (comma-separated), FAKE_INFO_DELAY and
FAKE_HEALTH_DELAY (seconds) in its environment control what it reports. `list_messages` returns no
mail and counts its calls in `next_cursor`; FAKE_LIST_FAILS makes it fail. The `fake_new_mail` tool
publishes the push event a `push` plugin sends when mail arrives.
"""

import os
import sys

import anyio

from mcp.server.mcpserver import Context, MCPServer

from mailbox_contract import INBOX_URI, Capability, Folders, Health, HealthCheck, ListMessagesOutput, MailboxInfo

server = MCPServer("fake-mailbox")


@server.tool()
async def mailbox_info() -> MailboxInfo:
    await anyio.sleep(float(os.environ.get("FAKE_INFO_DELAY", "0")))
    return MailboxInfo(
        contract_version=os.environ.get("FAKE_CONTRACT_VERSION", "1.0"),
        plugin_name="fake",
        plugin_version="0.0.1",
        account=os.environ.get("FAKE_ACCOUNT", "owner@example.com"),
        capabilities=[Capability(name) for name in os.environ.get("FAKE_CAPABILITIES", "").split(",") if name],
        folders=Folders(inbox="INBOX", archive="Archive", sent="Sent"),
    )


@server.tool()
async def health() -> Health:
    await anyio.sleep(float(os.environ.get("FAKE_HEALTH_DELAY", "0")))
    return Health(status="ok", checks=[HealthCheck(layer="plugin", ok=True, detail="ok")], repair_actions=[])


list_calls = 0


@server.tool()
async def list_messages(folder: str, cursor: str | None = None, limit: int = 100) -> ListMessagesOutput:
    global list_calls
    if os.environ.get("FAKE_LIST_FAILS"):
        raise RuntimeError("the fake mailbox is unavailable")
    list_calls += 1
    return ListMessagesOutput(messages=[], next_cursor=str(list_calls), has_more=False)


@server.tool()
async def fake_new_mail(context: Context) -> str:
    await context.notify_resource_updated(INBOX_URI)
    return "published"


if __name__ == "__main__":
    if sys.argv[1:2] == ["http"]:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run()
