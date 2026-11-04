# Gmail plugin (#96). GreenMail has no X-GM extensions, so Gmail's response parsing is tested
# on Gmail-format response bytes, and everything else (settings, push over IDLE, the tool set)
# against GreenMail behind the TLS stand-in. The whole contract runs live in
# tests/conformance with GMAIL_ADDRESS and GMAIL_APP_PASSWORD set.
import asyncio
import os
import sys
from email import message_from_bytes, policy
from email.message import EmailMessage

import pytest
from pydantic import ValidationError

from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from gmail_plugin.mailbox import (
    GmailMailbox, append_uid, gmail_ids, gmail_labels, probe_expunged, trash_folder,
)
from gmail_plugin.settings import GmailSettings
from imap_mailbox.mailbox import MailboxError
from mailbox_contract import INBOX_URI, Capability, ErrorCode, MailboxInfo
from tests.conformance.test_no_permanent_remove import DESTRUCTIVE_NAME
from tests.utils.mail_server import Mailbox
from tests.utils.tls_relay import fake_bridge

# The first line of Gmail's answer to UID FETCH n (X-GM-MSGID X-GM-THRID BODY.PEEK[]).
FETCH_LINE = b"7 (X-GM-THRID 1278455344230334865 X-GM-MSGID 1278455344230334866 UID 42 BODY[] {312}"
RAW_MESSAGE = (
    b"From: ana@example.com\r\nTo: owner@example.com\r\nSubject: Q3\r\n"
    b"Message-ID: <q3@example.com>\r\nX-GM-MSGID: 1\r\n\r\nThursday?\r\n"
)


def gmail(**overrides: object) -> GmailMailbox:
    return GmailMailbox(GmailSettings(account="owner@example.com", password="unused", **overrides))  # type: ignore[arg-type]


def parsed(raw: bytes) -> EmailMessage:
    message = message_from_bytes(raw, policy=policy.default)
    assert isinstance(message, EmailMessage)
    return message


# --- X-GM-MSGID / X-GM-THRID ----------------------------------------------------------


def test_ids_are_read_from_the_fetch_line():
    assert gmail_ids(FETCH_LINE) == {"MSGID": "1278455344230334866", "THRID": "1278455344230334865"}


def test_the_ref_is_the_servers_msgid_and_a_forged_header_is_replaced():
    mailbox, message = gmail(), parsed(RAW_MESSAGE)

    mailbox._add_server_headers(message, FETCH_LINE)
    summary = mailbox._summary(message)

    assert summary.ref == "1278455344230334866" and summary.message_id == "<q3@example.com>"
    assert message.get_all("X-GM-MSGID") == ["1278455344230334866"]
    assert message["X-GM-THRID"] == "1278455344230334865"


def test_a_fetch_without_msgid_is_an_error_not_a_message_without_a_ref():
    with pytest.raises(MailboxError) as raised:
        gmail()._add_server_headers(parsed(RAW_MESSAGE), b"7 (UID 42 BODY[] {312}")

    assert raised.value.code == ErrorCode.UNAVAILABLE


@pytest.mark.parametrize("ref", ["<q3@example.com>", "12 OR ALL", "1\r\nA1 LOGOUT", "١٢٣", "1" * 21, ""])
def test_refs_that_arent_gmail_ids_are_not_found_without_reaching_the_server(ref: str):
    assert gmail()._find_uid(None, "INBOX", ref) is None  # type: ignore[arg-type]  # never touched


# --- X-GM-LABELS ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "labels"),
    [
        ([b"3 (X-GM-LABELS (\\Inbox \\Important) UID 12)"], {"\\inbox", "\\important"}),
        ([b'3 (X-GM-LABELS ("\\\\Inbox" "\\\\Sent" Work) UID 12)'], {"\\inbox", "\\sent", "work"}),
        ([b'3 (X-GM-LABELS ("\\Inbox" "\\Important") UID 12)'], {"\\inbox", "\\important"}),
        ([b"3 (UID 12 X-GM-LABELS ())"], set()),
        ([b'3 (X-GM-LABELS ("Inbox (old)" "say \\"hi\\"") UID 12)'], {"inbox (old)", 'say "hi"'}),
        ([(b"3 (X-GM-LABELS (\\Important {6}", b"R\xc3\xa9sum"), b" \\Inbox) UID 12)"], {"\\important", "{6}", "\\inbox"}),
    ],
    ids=["atoms", "quoted", "loosely-quoted", "archived", "user-labels", "literal"],
)
def test_labels_are_parsed_from_gmail_responses(response: list[object], labels: set[str]):
    assert gmail_labels(response) == labels


def test_a_user_label_named_inbox_is_not_the_inbox():
    assert "\\inbox" not in gmail_labels([b'3 (X-GM-LABELS ("Inbox (old)" Inbox) UID 12)'])


def test_a_response_without_labels_is_an_error():
    with pytest.raises(MailboxError):
        gmail_labels([b"3 (UID 12)"])


# --- settings ---------------------------------------------------------------------------


def test_defaults_are_gmails_servers_and_folders():
    settings = gmail().settings

    assert (settings.imap_host, settings.imap_port, settings.smtp_host, settings.smtp_port) == (
        "imap.gmail.com", 993, "smtp.gmail.com", 465,
    )
    assert settings.tls == "ssl" and settings.username == "owner@example.com" and not settings.append_sent
    info = gmail().mailbox_info()
    assert info.folders.model_dump() == {"inbox": "INBOX", "archive": "[Gmail]/All Mail", "sent": "[Gmail]/Sent Mail"}
    assert info.capabilities == [Capability.PUSH] and info.plugin_name == "gmail"


def test_port_587_uses_starttls_unless_set_otherwise():
    assert gmail(smtp_port=587).settings.smtp_tls == "starttls"
    assert gmail(smtp_port=587, smtp_tls="ssl").settings.smtp_tls == "ssl"
    assert gmail().settings.smtp_tls is None


def test_gmail_connections_must_be_encrypted():
    for field in ("tls", "imap_tls", "smtp_tls"):
        with pytest.raises(ValidationError, match="TLS"):
            gmail(**{field: "none"})


def test_address_and_app_password_come_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAILBOX_ACCOUNT", "owner@example.com")
    monkeypatch.setenv("MAILBOX_PASSWORD", "unused")
    monkeypatch.setenv("MAILBOX_SMTP_PORT", "587")
    monkeypatch.setenv("MAILBOX_FOLDER_ARCHIVE", "[Google Mail]/All Mail")

    settings = GmailSettings()  # type: ignore[call-arg]

    assert settings.username == "owner@example.com" and settings.password == "unused"
    assert settings.smtp_tls == "starttls" and settings.folder_archive == "[Google Mail]/All Mail"


def test_the_plugin_refuses_to_start_without_an_app_password(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAILBOX_ACCOUNT", "owner@example.com")
    monkeypatch.delenv("MAILBOX_PASSWORD", raising=False)

    with pytest.raises(ValidationError, match="password"):
        GmailSettings()  # type: ignore[call-arg]


# --- the running plugin: push over IDLE ----------------------------------------------------


async def test_new_mail_is_pushed_over_idle_and_no_tool_removes_mail(mailbox: Mailbox):
    """The plugin as the app runs it (stdio, secrets via env_from), on GreenMail over pinned TLS."""
    bridge = fake_bridge()
    environment = {
        "MAILBOX_ACCOUNT": mailbox.address, "MAILBOX_PASSWORD": "unused",
        "MAILBOX_IMAP_HOST": "127.0.0.1", "MAILBOX_IMAP_PORT": str(bridge.imap_port),
        "MAILBOX_SMTP_HOST": "127.0.0.1", "MAILBOX_SMTP_PORT": str(bridge.smtp_port),
        "MAILBOX_CA_CERT_PATH": str(bridge.cert),
    }
    for name, value in environment.items():
        os.environ[f"GMAIL_TEST_{name}"] = value
    config = PluginConfig(id="gmail", transport=StdioTransport(
        type="stdio", command=sys.executable, args=["-m", "gmail_plugin.server"],
        env_from={name: f"GMAIL_TEST_{name}" for name in environment},
    ))
    registry = PluginRegistry()
    await registry.connect_all([config])
    try:
        assert registry.states["gmail"].status == "connected", registry.states["gmail"].reason
        client = registry.clients["gmail"]
        info = MailboxInfo.model_validate((await client.call_tool("mailbox_info", {})).structured_content)
        tools = [tool.name for tool in (await client.list_tools()).tools]
        assert Capability.PUSH in info.capabilities
        assert tools and not [name for name in tools if DESTRUCTIVE_NAME.search(name)]

        async with client.listen(resource_subscriptions=[INBOX_URI]) as subscription:
            async def deliver_until_pushed() -> None:
                # Mail that lands before the plugin is idling (or before the stream is
                # acknowledged) isn't pushed, so keep delivering.
                while True:
                    await asyncio.to_thread(mailbox.deliver, sender="ana@example.com", subject="new", body="x")
                    await asyncio.sleep(1)

            delivering = asyncio.create_task(deliver_until_pushed())
            try:
                event = await asyncio.wait_for(anext(aiter(subscription)), timeout=30)
            finally:
                delivering.cancel()
        assert INBOX_URI in str(event)
    finally:
        await registry.close()


# --- setup: Gmail's Auto-Expunge setting (#97) ------------------------------------------
# IMAP doesn't report the setting, so the plugin probes: it appends a message to the Trash, marks
# only that message \Deleted and sees whether Gmail drops it at once. GreenMail never auto-expunges
# (the "off" case); the "on" case is Gmail's response data here and the live run in
# test_gmail_setup_live.py.

GMAIL_LIST = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"',
    b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Papierkorb"',
]


def test_the_trash_is_found_by_its_special_use_flag_whatever_its_name():
    assert trash_folder(GMAIL_LIST) == "[Gmail]/Papierkorb"


def test_without_a_special_use_trash_the_english_name_is_assumed():
    assert trash_folder([b'() "." "INBOX"', b'() "." "Trash-ish"']) == "[Gmail]/Trash"


def test_the_probes_uid_comes_from_appenduid():
    assert append_uid([b"[APPENDUID 663 4521] (Success)"]) == ("663", 4521)
    assert append_uid([b"APPEND completed."]) is None


@pytest.mark.parametrize(
    ("response", "expunged"),
    [([None], True), ([b"5 (UID 42 FLAGS (\\Deleted))"], False), ([b"5 (FLAGS (\\Seen \\Deleted) UID 42)"], False)],
    ids=["gone", "kept", "kept-seen"],
)
def test_a_probe_gmail_drops_at_once_means_auto_expunge_is_on(response: list[object], expunged: bool):
    assert probe_expunged(response) is expunged


def test_a_probe_that_kept_no_deleted_flag_tells_nothing():
    with pytest.raises(MailboxError):
        probe_expunged([b"5 (UID 42 FLAGS (\\Seen))"])


def on_greenmail(mailbox: Mailbox) -> GmailMailbox:
    bridge = fake_bridge()
    return GmailMailbox(GmailSettings(  # type: ignore[call-arg]  # the rest default
        account=mailbox.address, imap_host="127.0.0.1", imap_port=bridge.imap_port,
        password="unused",
        smtp_host="127.0.0.1", smtp_port=bridge.smtp_port, ca_cert_path=str(bridge.cert),
    ))


def flags_by_message_id(mailbox: Mailbox, folder: str) -> dict[str, bytes]:
    with mailbox.imap() as connection:
        connection.select(folder, readonly=True)
        _, data = connection.uid("FETCH", "1:*", "(FLAGS BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    return {parsed(item[1])["Message-ID"]: item[0] for item in data if isinstance(item, tuple)}


def test_with_auto_expunge_off_there_is_no_warning_and_only_the_probe_is_marked(mailbox: Mailbox):
    trash = '"[Gmail]/Trash"'
    mailbox.create_folder(trash)
    in_inbox = mailbox.deliver(sender="ana@example.com", subject="keep", body="x")
    in_trash = mailbox.append(trash, sender="ana@example.com", subject="trashed by the owner", body="x")
    # Another mail app marked this one deleted: a CLOSE or EXPUNGE anywhere in the probe would remove it.
    marked = mailbox.append(trash, sender="ana@example.com", subject="marked by another app", body="x")
    with mailbox.imap() as connection:
        connection.select(trash)
        connection.uid("STORE", "1:*", "+FLAGS.SILENT", "(\\Deleted)")
        connection.uid("STORE", "1", "-FLAGS.SILENT", "(\\Deleted)")  # in_trash, appended first

    assert on_greenmail(mailbox).setup_warnings().warnings == []

    trash_flags = flags_by_message_id(mailbox, trash)
    probes = [flags for message_id, flags in trash_flags.items() if message_id not in (in_trash, marked)]
    assert len(probes) == 1 and b"\\Deleted" in probes[0]
    assert b"\\Deleted" not in trash_flags[in_trash] and b"\\Deleted" in trash_flags[marked]
    assert b"\\Deleted" not in flags_by_message_id(mailbox, "INBOX")[in_inbox]


def test_when_the_probe_cannot_run_the_owner_is_told_to_check_the_setting(mailbox: Mailbox):
    # No Trash folder on this server, so there's nowhere to put the probe.
    [warning] = on_greenmail(mailbox).setup_warnings().warnings

    assert "couldn't check" in warning.lower() and "Auto-Expunge" in warning
