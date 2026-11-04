"""A minimal real mailbox/1 MCP server for tests (stdio by default, `http <port>` for HTTP).

FAKE_CONTRACT_VERSION, FAKE_ACCOUNT, FAKE_CAPABILITIES (comma-separated), FAKE_INFO_DELAY and
FAKE_HEALTH_DELAY (seconds) in its environment control what it reports. `list_messages` returns no
mail and counts its calls in `next_cursor`; FAKE_LIST_FAILS makes it fail and FAKE_LIST_DELAY slow. The `fake_new_mail` tool
publishes the push event a `push` plugin sends when mail arrives. FAKE_INBOX_CONTAINS (`extra` or
`missing`) adds an `inbox_contains` that breaks the exact-keys rule that way; `present` answers every
ref as in the inbox, `absent` as out of it. FAKE_ARCHIVE=unverified adds an `archive` whose move is never verified; `malformed`, one that answers
outside the contract; `slow`, one that takes 30 s. FAKE_RESTORE=slow and FAKE_SEND=slow
add a `restore` and a `send` that take 30 s.
"""

import os
import sys

import anyio

from mcp.server.mcpserver import Context, MCPServer

from mailbox_contract import INBOX_URI, Capability, Folders, Health, HealthCheck, ListMessagesOutput, MailboxInfo, MoveResult

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
    await anyio.sleep(float(os.environ.get("FAKE_LIST_DELAY", "0")))
    list_calls += 1
    return ListMessagesOutput(messages=[], next_cursor=str(list_calls), has_more=False)


if os.environ.get("FAKE_INBOX_CONTAINS"):

    @server.tool()
    async def inbox_contains(refs: list[str]) -> dict[str, bool]:
        answer = {ref: os.environ["FAKE_INBOX_CONTAINS"] != "absent" for ref in refs}
        if os.environ["FAKE_INBOX_CONTAINS"] == "extra":
            answer["not-asked-about"] = False
        elif os.environ["FAKE_INBOX_CONTAINS"] == "missing":
            answer.pop(refs[0])
        return answer


if os.environ.get("FAKE_ARCHIVE") == "unverified":

    @server.tool()
    async def archive(ref: str) -> MoveResult:
        return MoveResult(ok=True, verified=False)

elif os.environ.get("FAKE_ARCHIVE") == "slow":

    @server.tool()
    async def archive(ref: str) -> MoveResult:
        await anyio.sleep(30)
        return MoveResult(ok=True, verified=True)

elif os.environ.get("FAKE_ARCHIVE") == "malformed":

    @server.tool()
    async def archive(ref: str) -> dict[str, str]:
        return {"moved": "probably"}


if os.environ.get("FAKE_RESTORE") == "slow":

    @server.tool()
    async def restore(ref: str) -> MoveResult:
        await anyio.sleep(30)
        return MoveResult(ok=True, verified=True)


if os.environ.get("FAKE_SEND") == "slow":

    @server.tool()
    async def send(to: list[dict[str, str]], subject: str, body_text: str, cc: list[dict[str, str]] | None = None,
                   in_reply_to_ref: str | None = None) -> dict[str, object]:
        await anyio.sleep(30)
        return {"ok": True, "sent_message_id": "<sent@fake>"}


@server.tool()
async def fake_new_mail(context: Context) -> str:
    await context.notify_resource_updated(INBOX_URI)
    return "published"


if __name__ == "__main__":
    if sys.argv[1:2] == ["http"]:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run()
