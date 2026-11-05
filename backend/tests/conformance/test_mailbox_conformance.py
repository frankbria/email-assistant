# mailbox/1 conformance suite (spec §5.5): run against every plugin target in TARGETS.
# A plugin is "supported" only when this passes. The plugin runs as a real MCP server
# process, connected the way the app connects it; mail lives on the GreenMail test server, or
# for the Gmail target on a disposable Gmail account (set GMAIL_ADDRESS and GMAIL_APP_PASSWORD).
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from mcp import Client
from pydantic import BaseModel

import mailbox_contract as contract
from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from tests.conformance.test_no_permanent_remove import DESTRUCTIVE_NAME
from tests.utils.gmail_account import ADDRESS_ENV, APP_KEY_ENV, GMAIL_ADDRESS, GMAIL_APP_KEY, gmail_account
from tests.utils.mail_server import IMAP_PORT, MAIL_HOST, SMTP_PORT, Mailbox, new_mailbox
from tests.utils.tls_relay import fake_bridge


def greenmail_mailbox() -> Mailbox:
    mailbox = new_mailbox()
    for folder in ("Archive", "Sent"):  # every real mailbox has both
        mailbox.create_folder(folder)
    return mailbox


@dataclass
class Target:
    name: str
    plugin_config: Callable[[Mailbox], PluginConfig]
    mailbox: Callable[[], Mailbox] = greenmail_mailbox
    # Where sent mail is delivered: another GreenMail mailbox, or the live account itself.
    recipient: Callable[[Mailbox], Mailbox] = lambda _: new_mailbox()
    greenmail: bool = True


def reference_imap_plugin(mailbox: Mailbox, plugin_id: str = "reference-imap", **overrides: str) -> PluginConfig:
    """`overrides` replace settings, e.g. MAILBOX_SMTP_PORT="1" for a mailbox that can't send."""
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
    } | overrides
    # plugins.yaml passes values through env_from references; mirror that, one set per plugin id.
    prefix = f"CONFORMANCE_{plugin_id.upper().replace('-', '_')}"
    for name, value in settings.items():
        os.environ[f"{prefix}_{name}"] = value
    return PluginConfig(
        id=plugin_id,
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=["-m", "imap_mailbox.server"],
            env_from={name: f"{prefix}_{name}" for name in settings},
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
        # GreenMail neither authenticates SMTP nor files sent mail; Bridge does both. So this
        # target proves the Proton plugin's mailbox/1 behaviour over pinned TLS, not parity
        # with a live Bridge (checked on the owner's machine, #53).
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


def gmail_plugin(mailbox: Mailbox) -> PluginConfig:
    """The live account's address and app password come straight from the environment."""
    return PluginConfig(
        id="gmail",
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=["-m", "gmail_plugin.server"],
            env_from={"MAILBOX_ACCOUNT": ADDRESS_ENV, "MAILBOX_PASSWORD": APP_KEY_ENV},
        ),
    )


# Each supported plugin adds a target here.
TARGETS = [
    pytest.param(Target("reference-imap", reference_imap_plugin), id="reference-imap"),
    pytest.param(Target("proton", proton_plugin), id="proton"),
    # GreenMail has no X-GM extensions, so Gmail runs only live, against a disposable account.
    pytest.param(
        Target("gmail", gmail_plugin, mailbox=gmail_account, recipient=lambda account: account, greenmail=False),
        id="gmail",
        marks=pytest.mark.skipif(not (GMAIL_ADDRESS and GMAIL_APP_KEY), reason="live Gmail run: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD"),
    ),
]

pytestmark = pytest.mark.parametrize("target", TARGETS)


@pytest.fixture(autouse=True)
def test_mail_server(request: pytest.FixtureRequest, target: Target) -> None:
    if target.greenmail:
        request.getfixturevalue("mail_server")


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

    async def ref(self, message_id: str) -> str:
        """The plugin's ref for an inbox message, as the app learns it: from list_messages."""
        arguments: dict[str, object] = {"folder": "inbox", "limit": 500}
        while True:
            page = await self.call_as("list_messages", contract.ListMessagesOutput, arguments)
            refs = [m.ref for m in page.messages if m.message_id == message_id]
            if refs:
                return refs[0]
            assert page.has_more, f"{message_id} isn't listed in the inbox"
            arguments = {"folder": "inbox", "cursor": page.next_cursor, "limit": 500}


@asynccontextmanager
async def open_session(target: Target) -> AsyncIterator[Session]:
    """Used inside each test body: MCP clients must close in the task that opened them."""
    mailbox = target.mailbox()
    registry = PluginRegistry()
    await registry.connect_all([target.plugin_config(mailbox)])
    try:
        state = registry.states[target.plugin_config(mailbox).id]
        assert state.status == "connected", state.reason
        yield Session(client=registry.clients[state.id], mailbox=mailbox)
    finally:
        await registry.close()


def every_message_id(mailbox: Mailbox) -> set[str]:
    return {str(message["Message-ID"]) for folder in ("INBOX", "Archive", "Sent") for message in mailbox.messages(folder)}


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
        resumed = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "inbox", "cursor": second.next_cursor})
        assert [m.message_id for m in resumed.messages] == [newest]


async def test_a_since_listing_keeps_its_window_across_pages_and_ends_past_older_mail(target: Target):
    """Imported history can sit at higher UIDs than recent mail; it stays out of the window."""
    async with open_session(target) as session:

        def received(days: int, subject: str) -> str:
            ago = datetime.now(UTC) - timedelta(days=days)
            return session.mailbox.append("INBOX", sender="ana@example.com", subject=subject, body="x", received=ago)

        recent_1, _, recent_2, _ = received(2, "r1"), received(30, "o1"), received(3, "r2"), received(40, "o2")
        listed: list[str] = []
        page = contract.ListMessagesOutput(messages=[], next_cursor="", has_more=True)
        arguments: dict[str, object] = {"folder": "inbox", "since": (datetime.now(UTC) - timedelta(days=14)).isoformat()}
        while page.has_more:
            page = await session.call_as("list_messages", contract.ListMessagesOutput, {**arguments, "limit": 1})
            listed += [m.message_id for m in page.messages]
            arguments = {"folder": "inbox", "cursor": page.next_cursor}

        assert listed == [recent_1, recent_2]
        newest = session.mailbox.deliver(sender="ana@example.com", subject="new", body="x")
        resumed = await session.call_as("list_messages", contract.ListMessagesOutput, arguments)
        assert [m.message_id for m in resumed.messages] == [newest]


async def test_empty_page_still_returns_a_cursor(target: Target):
    async with open_session(target) as session:
        page = await session.call_as("list_messages", contract.ListMessagesOutput, {"folder": "inbox"})

        assert page.messages == [] and page.next_cursor


async def test_list_messages_reads_sent(target: Target):
    async with open_session(target) as session:
        # A live account's Sent isn't empty: list to its end first.
        page = contract.ListMessagesOutput(messages=[], next_cursor="", has_more=True)
        arguments: dict[str, object] = {"folder": "sent", "limit": 500}
        while page.has_more:
            page = await session.call_as("list_messages", contract.ListMessagesOutput, arguments)
            arguments = {"folder": "sent", "cursor": page.next_cursor, "limit": 500}
        sent_id = session.mailbox.append("Sent", sender=session.mailbox.address, to="ana@example.com", subject="Sent one", body="Hi")

        page = await session.call_as("list_messages", contract.ListMessagesOutput, arguments)

        assert [m.message_id for m in page.messages] == [sent_id]


async def test_invalid_cursor_is_a_typed_error(target: Target):
    async with open_session(target) as session:
        error = await session.call_error("list_messages", {"folder": "inbox", "cursor": "999:1"})

        assert error.code == contract.ErrorCode.INVALID_CURSOR


async def test_inbox_contains_answers_exactly_the_requested_refs(target: Target):
    async with open_session(target) as session:
        present = await session.ref(session.mailbox.deliver(sender="ana@example.com", subject="here", body="x"))
        refs = [present, "<absent@example.com>"]

        answer = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": refs})

        assert answer.root == {present: True, "<absent@example.com>": False}


async def test_get_message_returns_text_headers_and_attachment_metadata(target: Target):
    async with open_session(target) as session:
        message_id = session.mailbox.deliver(sender="ana@example.com", subject="Q3 budget", body="Can we meet Thursday?")
        ref = await session.ref(message_id)

        detail = await session.call_as("get_message", contract.MessageDetail, {"ref": ref})

        assert detail.ref == ref and detail.message_id == message_id and detail.subject == "Q3 budget"
        assert detail.text.strip() == "Can we meet Thursday?"
        assert any(header.name.lower() == "message-id" for header in detail.headers)
        assert detail.attachments == []


async def test_archive_then_restore_round_trips(target: Target):
    async with open_session(target) as session:
        message_id = session.mailbox.deliver(sender="ana@example.com", subject="round trip", body="x")
        ref = await session.ref(message_id)

        archived = await session.call_as("archive", contract.MoveResult, {"ref": ref})
        after_archive = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": [ref]})
        restored = await session.call_as("restore", contract.MoveResult, {"ref": ref})
        after_restore = await session.call_as("inbox_contains", contract.InboxContainsOutput, {"refs": [ref]})

        assert archived.ok and archived.verified and after_archive.root == {ref: False}
        assert message_id in {str(m["Message-ID"]) for m in session.mailbox.messages("Archive")} or after_restore
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
        recipient = target.recipient(session.mailbox)

        sent = await session.call_as(
            "send",
            contract.SendResult,
            {
                "to": [{"email": recipient.address}],
                "subject": "Re: Q3 budget",
                "body_text": "Thursday at 3 works.",
                "in_reply_to_ref": await session.ref(original),
            },
        )

        deadline = asyncio.get_running_loop().time() + 60
        while not (delivered := [m for m in recipient.messages("INBOX") if m["Message-ID"] == sent.sent_message_id]):
            assert asyncio.get_running_loop().time() < deadline, "reply never arrived"
            await asyncio.sleep(0.2)
        [reply] = delivered
        assert sent.ok
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
        first, second = await session.ref(first), await session.ref(second)
        await session.call("get_message", {"ref": first})
        await session.call("archive", {"ref": first})
        await session.call("archive", {"ref": second})
        await session.call("restore", {"ref": first})
        await session.call("send", {"to": [{"email": target.recipient(box).address}], "subject": "s", "body_text": "b"})
        await session.call_error("archive", {"ref": "<no-such-message@example.com>"})

        assert seeded <= every_message_id(box)


async def test_no_tool_is_named_like_a_permanent_remove(target: Target):
    """AC-1.2 for every plugin, not only the reference one: the tool list has no delete/expunge."""
    async with open_session(target) as session:
        names = [tool.name for tool in (await session.client.list_tools()).tools]

        assert names and not [name for name in names if DESTRUCTIVE_NAME.search(name)]


async def test_a_push_plugin_announces_new_mail(target: Target):
    """Only for plugins listing `push`: new inbox mail publishes an update on mailbox://inbox."""
    async with open_session(target) as session:
        info = await session.call_as("mailbox_info", contract.MailboxInfo)
        if contract.Capability.PUSH not in info.capabilities:
            pytest.skip(f"{target.name} doesn't offer push")

        async with session.client.listen(resource_subscriptions=[contract.INBOX_URI]) as subscription:

            async def deliver_until_pushed() -> None:
                # Mail that lands before the plugin is idling isn't pushed, so keep delivering.
                while True:
                    await asyncio.to_thread(session.mailbox.deliver, sender="ana@example.com", subject="new", body="x")
                    await asyncio.sleep(2)

            delivering = asyncio.create_task(deliver_until_pushed())
            try:
                event = await asyncio.wait_for(anext(aiter(subscription)), timeout=60)
            finally:
                delivering.cancel()
        assert contract.INBOX_URI in str(event)
