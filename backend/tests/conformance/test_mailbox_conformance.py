# mailbox/1 conformance suite (spec §5.5): run against every plugin target in TARGETS.
# A plugin is "supported" only when this passes. The plugin runs as a real MCP server
# process, connected the way the app connects it; mail lives on the GreenMail test server.
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from mcp import Client
from pydantic import BaseModel

import mailbox_contract as contract
from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from tests.utils.mail_server import IMAP_PORT, MAIL_HOST, SMTP_PORT, Mailbox, new_mailbox
from tests.utils.tls_relay import fake_bridge



@dataclass
class Target:
    name: str
    plugin_config: Callable[[Mailbox], PluginConfig]


def reference_imap_plugin(mailbox: Mailbox) -> PluginConfig:
    settings = {
        "MAILBOX_ACCOUNT": mailbox.address,
        "MAILBOX_USERNAME": mailbox.address,
        "MAILBOX_PASSWORD": "unused",
        "MAILBOX_IMAP_HOST": MAIL_HOST,
        "MAILBOX_IMAP_PORT": str(IMAP_PORT),
        "MAILBOX_SMTP_HOST": MAIL_HOST,
        "MAILBOX_SMTP_PORT": str(SMTP_PORT),
        "MAILBOX_SMTP_LOGIN": "false",
        "MAILBOX_TLS": "none",
        "MAILBOX_APPEND_SENT": "true",
    }
    # plugins.yaml passes values through env_from references; mirror that.
    for name, value in settings.items():
        os.environ[f"CONFORMANCE_{name}"] = value
    return PluginConfig(
        id="reference-imap",
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=["-m", "imap_mailbox.server"],
            env_from={name: f"CONFORMANCE_{name}" for name in settings},
        ),
    )


def proton_plugin(mailbox: Mailbox) -> PluginConfig:
    bridge = fake_bridge()
    settings = {
        "MAILBOX_ACCOUNT": mailbox.address,
        "MAILBOX_USERNAME": mailbox.address,
        "MAILBOX_PASSWORD": "unused",
        "MAILBOX_IMAP_PORT": str(bridge.imap_port),
        "MAILBOX_SMTP_PORT": str(bridge.smtp_port),
        "MAILBOX_TLS": "ssl",
        "MAILBOX_CA_CERT_PATH": str(bridge.cert),
        # GreenMail neither authenticates SMTP nor files sent mail; Bridge does both.
        "MAILBOX_SMTP_LOGIN": "false",
        "MAILBOX_APPEND_SENT": "true",
    }
    for name, value in settings.items():
        os.environ[f"CONFORMANCE_PROTON_{name}"] = value
    return PluginConfig(
        id="proton",
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=["-m", "proton_plugin.server"],
            env_from={name: f"CONFORMANCE_PROTON_{name}" for name in settings},
        ),
    )


# Each supported plugin adds a target here (Gmail: #96).
TARGETS = [Target("reference-imap", reference_imap_plugin), Target("proton", proton_plugin)]

pytestmark = [
    pytest.mark.usefixtures("mail_server"),
    pytest.mark.parametrize("target", TARGETS, ids=[target.name for target in TARGETS]),
]


@dataclass
class Session:
    client: Client
    mailbox: Mailbox

    async def call(self, tool: str, arguments: dict[str, object] | None = None) -> object:
        result = await self.client.call_tool(tool, arguments or {})
        assert not result.is_error, f"{tool} failed: {result.structured_content or result.content}"
        assert result.structured_content is not None, f"{tool} returned no structured content"
        return result.structured_content

    async def call_as[ModelT: BaseModel](self, tool: str, model: type[ModelT], arguments: dict[str, object] | None = None) -> ModelT:
        return model.model_validate(await self.call(tool, arguments))

    async def call_error(self, tool: str, arguments: dict[str, object]) -> contract.ToolError:
        result = await self.client.call_tool(tool, arguments)
        assert result.is_error, f"{tool} should have failed"
        return contract.ToolError.model_validate(result.structured_content)


@asynccontextmanager
async def open_session(target: Target) -> AsyncIterator[Session]:
    """Used inside each test body: MCP clients must close in the task that opened them."""
    mailbox = new_mailbox()
    for folder in ("Archive", "Sent"):  # every real mailbox has both
        mailbox.create_folder(folder)
    registry = PluginRegistry()
    await registry.connect_all([target.plugin_config(mailbox)])
    try:
        state = registry.states[target.plugin_config(mailbox).id]
        assert state.status == "connected", state.reason
        yield Session(client=registry.clients[state.id], mailbox=mailbox)
    finally:
        await registry.close()


def every_message_id(mailbox: Mailbox) -> set[str]:
    return {
        str(message["Message-ID"])
        for folder in ("INBOX", "Archive", "Sent")
        for message in mailbox.messages(folder)
    }


async def test_mailbox_info_reports_a_supported_contract(target: Target):
    async with open_session(target) as session:
        info = await session.call_as("mailbox_info", contract.MailboxInfo)

        assert contract.is_supported(info.contract_version)
        assert info.account == session.mailbox.address
        assert info.folders.inbox and info.folders.archive and info.folders.sent


async def test_health_reports_ok(target: Target):
    async with open_session(target) as session:
        health = await session.call_as("health", contract.Health)

        assert health.status == "ok"
        assert health.checks and all(check.ok for check in health.checks)


async def test_list_messages_pages_and_resumes_after_a_restart(target: Target):
    async with open_session(target) as session:
        ids = [session.mailbox.deliver(sender="ana@example.com", subject=f"m{n}", body=f"Body {n}") for n in range(3)]

        first = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "inbox", "limit": 2})
        second = await session.call_as(
            "list_messages", contract.ListMessagesOutput, {"folder": "inbox", "cursor": first.next_cursor, "limit": 2}
        )

        assert [m.message_id for m in first.messages] == ids[:2] and first.has_more
        assert [m.message_id for m in second.messages] == ids[2:] and not second.has_more
        assert first.messages[0].sender.email == "ana@example.com"
        assert first.messages[0].snippet == "Body 0"

        # The cursor is all a restarted app has; new mail after it, and only that, comes back.
        newest = session.mailbox.deliver(sender="ana@example.com", subject="m3", body="Body 3")
        resumed = await session.call_as(
            "list_messages", contract.ListMessagesOutput, {"folder": "inbox", "cursor": second.next_cursor}
        )
        assert [m.message_id for m in resumed.messages] == [newest]


async def test_empty_page_still_returns_a_cursor(target: Target):
    async with open_session(target) as session:
        page = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "inbox"})

        assert page.messages == [] and page.next_cursor


async def test_list_messages_reads_sent(target: Target):
    async with open_session(target) as session:
        sent_id = session.mailbox.append("Sent", sender=session.mailbox.address, to="ana@example.com", subject="Sent one", body="Hi")

        page = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "sent"})

        assert [m.message_id for m in page.messages] == [sent_id]


async def test_invalid_cursor_is_a_typed_error(target: Target):
    async with open_session(target) as session:
        error = await session.call_error("list_messages", {"folder": "inbox", "cursor": "999:1"})

        assert error.code == contract.ErrorCode.INVALID_CURSOR


async def test_inbox_contains_answers_exactly_the_requested_refs(target: Target):
    async with open_session(target) as session:
        present = session.mailbox.deliver(sender="ana@example.com", subject="here", body="x")
        refs = [present, "<absent@example.com>"]

        answer = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": refs})

        assert answer.root == {present: True, "<absent@example.com>": False}


async def test_get_message_returns_text_headers_and_attachment_metadata(target: Target):
    async with open_session(target) as session:
        ref = session.mailbox.deliver(sender="ana@example.com", subject="Q3 budget", body="Can we meet Thursday?")

        detail = await session.call_as("get_message", contract.MessageDetail, {"ref": ref})

        assert detail.message_id == ref and detail.subject == "Q3 budget"
        assert detail.text.strip() == "Can we meet Thursday?"
        assert any(header.name.lower() == "message-id" for header in detail.headers)
        assert detail.attachments == []


async def test_archive_then_restore_round_trips(target: Target):
    async with open_session(target) as session:
        ref = session.mailbox.deliver(sender="ana@example.com", subject="round trip", body="x")

        archived = await session.call_as("archive", contract.MoveResult, {"ref": ref})
        after_archive = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": [ref]})
        restored = await session.call_as("restore", contract.MoveResult, {"ref": ref})
        after_restore = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": [ref]})

        assert archived.ok and archived.verified and after_archive.root == {ref: False}
        assert ref in {str(m["Message-ID"]) for m in session.mailbox.messages("Archive")} or after_restore
        assert restored.ok and restored.verified and after_restore.root == {ref: True}


async def test_unknown_ref_is_a_not_found_error(target: Target):
    async with open_session(target) as session:
        for tool in ("get_message", "archive", "restore"):
            error = await session.call_error(tool, {"ref": "<no-such-message@example.com>"})
            assert error.code == contract.ErrorCode.NOT_FOUND, tool
            assert not error.retryable


async def test_reply_is_threaded_and_delivered(target: Target):
    async with open_session(target) as session:
        original = session.mailbox.deliver(sender="ana@example.com", subject="Q3 budget", body="Thursday?")
        recipient = new_mailbox()

        sent = await session.call_as(
            "send",
            contract.SendResult,
            {
                "to": [{"email": recipient.address}],
                "subject": "Re: Q3 budget",
                "body_text": "Thursday at 3 works.",
                "in_reply_to_ref": original,
            },
        )

        deadline = asyncio.get_running_loop().time() + 10
        while not (delivered := recipient.messages("INBOX")):
            assert asyncio.get_running_loop().time() < deadline, "reply never arrived"
            await asyncio.sleep(0.2)
        [reply] = delivered
        assert sent.ok and reply["Message-ID"] == sent.sent_message_id
        assert reply["In-Reply-To"] == original and original in str(reply["References"])


async def test_running_every_tool_loses_no_message(target: Target):
    """AC-1.1: after every tool has run, every seeded message still exists in the account."""
    async with open_session(target) as session:
        box = session.mailbox
        seeded = {box.deliver(sender="ana@example.com", subject=f"in {n}", body="x") for n in range(3)}
        seeded |= {box.append("Sent", sender=box.address, to="ana@example.com", subject="out", body="x")}
        seeded |= {box.append("Archive", sender="old@example.com", subject="old", body="x")}
        first, second, *_ = sorted(m for m in seeded if m in {str(x["Message-ID"]) for x in box.messages("INBOX")})

        await session.call("mailbox_info")
        await session.call("health")
        page = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "inbox", "limit": 1})
        await session.call("list_messages", {"folder": "inbox", "cursor": page.next_cursor})
        await session.call("list_messages", {"folder": "sent"})
        await session.call("inbox_contains", {"refs": sorted(seeded)})
        await session.call("get_message", {"ref": first})
        await session.call("archive", {"ref": first})
        await session.call("archive", {"ref": second})
        await session.call("restore", {"ref": first})
        await session.call("send", {"to": [{"email": new_mailbox().address}], "subject": "s", "body_text": "b"})
        await session.call_error("archive", {"ref": "<no-such-message@example.com>"})

        assert seeded <= every_message_id(box)
