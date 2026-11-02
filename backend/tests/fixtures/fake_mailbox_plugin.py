"""A minimal real mailbox/1 MCP server for tests (stdio by default, `http <port>` for HTTP).

FAKE_CONTRACT_VERSION, FAKE_ACCOUNT and FAKE_HEALTH_DELAY (seconds) in its environment
control what it reports.
"""

import os
import sys

import anyio

from mcp.server.mcpserver import MCPServer

from mailbox_contract import Folders, Health, HealthCheck, MailboxInfo

server = MCPServer("fake-mailbox")


@server.tool()
def mailbox_info() -> MailboxInfo:
    return MailboxInfo(
        contract_version=os.environ.get("FAKE_CONTRACT_VERSION", "1.0"),
        plugin_name="fake",
        plugin_version="0.0.1",
        account=os.environ.get("FAKE_ACCOUNT", "owner@example.com"),
        capabilities=[],
        folders=Folders(inbox="INBOX", archive="Archive", sent="Sent"),
    )


@server.tool()
async def health() -> Health:
    await anyio.sleep(float(os.environ.get("FAKE_HEALTH_DELAY", "0")))
    return Health(status="ok", checks=[HealthCheck(layer="plugin", ok=True, detail="ok")], repair_actions=[])


if __name__ == "__main__":
    if sys.argv[1:2] == ["http"]:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run()
