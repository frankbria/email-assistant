# Proton plugin skeleton (#43). Bridge is stood in for by a real TLS front-end (a
# generated certificate valid for 127.0.0.1) relaying to the GreenMail test server.
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.plugins.config import HttpTransport, PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from proton_plugin.mailbox import ProtonMailbox
from proton_plugin.mutf7 import decode_mutf7
from proton_plugin.settings import ProtonSettings, load_settings
from tests.utils.mail_server import Mailbox
from tests.utils.tls_relay import fake_bridge


@pytest.fixture(scope="module")
def bridge(mail_server: None) -> dict[str, object]:
    stand_in = fake_bridge()
    return {"cert": stand_in.cert, "wrong_cert": stand_in.wrong_cert, "imap_port": stand_in.imap_port, "smtp_port": stand_in.smtp_port}


def proton_settings(mailbox: Mailbox, bridge: dict[str, object], cert: str = "cert") -> ProtonSettings:
    return ProtonSettings(
        account=mailbox.address, username=mailbox.address, password="unused", tls="ssl",
        imap_port=bridge["imap_port"], smtp_port=bridge["smtp_port"], smtp_login=False,
        ca_cert_path=str(bridge[cert]),
    )


@pytest.mark.parametrize(
    ("encoded", "decoded"),
    [
        ("Folders/&AOk-t&AOk-", "Folders/été"),
        ("Labels/&ZeVnLIqe-", "Labels/日本語"),
        ("R&-D", "R&D"),
        ("INBOX", "INBOX"),
        ("Broken&AOk", "Broken&AOk"),  # unterminated: kept as-is
        ("Bad&!!!-", "Bad&!!!-"),  # not base64: kept as-is
    ],
)
def test_folder_names_decode_from_modified_utf7(encoded: str, decoded: str):
    assert decode_mutf7(encoded) == decoded


MINIMAL_SETTINGS: dict[str, str] = {
    "account": "a@b.c",
    "username": "a",
    "password": "p",
    "ca_cert_path": "c.pem",
}


def test_bridge_connections_must_be_encrypted():
    with pytest.raises(ValidationError, match="TLS"):
        ProtonSettings(**MINIMAL_SETTINGS, tls="none")


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "203.0.113.5"])
def test_http_mode_binds_only_to_tailscale_or_loopback(host: str):
    with pytest.raises(ValidationError, match="Tailscale"):
        ProtonSettings(**MINIMAL_SETTINGS, http_host=host)


@pytest.mark.parametrize("host", ["100.101.102.103", "fd7a:115c:a1e0::1", "127.0.0.1"])
def test_http_mode_accepts_tailscale_and_loopback(host: str):
    assert ProtonSettings(**MINIMAL_SETTINGS, http_host=host).http_host == host


def test_pinned_bridge_certificate_gives_a_healthy_connection(mailbox: Mailbox, bridge: dict[str, object]):
    mailbox.append("Archive", sender="setup@example.com", subject="x", body="x")
    mailbox.append("Sent", sender=mailbox.address, subject="x", body="x")

    health = ProtonMailbox(proton_settings(mailbox, bridge)).health()

    assert health.status == "ok", health


def test_wrong_pinned_certificate_fails_in_plain_language(mailbox: Mailbox, bridge: dict[str, object]):
    health = ProtonMailbox(proton_settings(mailbox, bridge, cert="wrong_cert")).health()

    [imap] = [check for check in health.checks if check.layer == "imap_login"]
    assert health.status == "down" and not imap.ok
    assert "doesn't match the pinned one" in imap.detail and "Export it again from Bridge" in imap.detail


def test_folder_map_groups_and_decodes_bridge_folders(mailbox: Mailbox, bridge: dict[str, object]):
    for folder in ("Archive", "Folders/&AOk-t&AOk-", "Labels/&ZeVnLIqe-", 'Folders/Say "hi"'):
        mailbox.append(folder, sender="setup@example.com", subject="x", body="x")

    folders = ProtonMailbox(proton_settings(mailbox, bridge)).folder_map()

    assert "Archive" in folders["system"] and "INBOX" in folders["system"]
    assert sorted(folders["folders"]) == ['Say "hi"', "été"] and folders["labels"] == ["日本語"]


def test_custom_archive_folder_counts_as_present(mailbox: Mailbox, bridge: dict[str, object]):
    for folder in ("Folders/Done", "Sent"):
        mailbox.append(folder, sender="setup@example.com", subject="x", body="x")
    settings = proton_settings(mailbox, bridge).model_copy(update={"folder_archive": "Folders/Done"})

    assert ProtonMailbox(settings).health().status == "ok"


def test_wrong_security_mode_fails_in_plain_language(mailbox: Mailbox, bridge: dict[str, object]):
    # Bridge's port speaks implicit TLS but the plugin is set to STARTTLS.
    settings = proton_settings(mailbox, bridge).model_copy(update={"tls": "starttls"})

    [imap] = [check for check in ProtonMailbox(settings).health().checks if check.layer == "imap_login"]

    assert not imap.ok and "security" in imap.detail.lower()


def plugin_environment(mailbox: Mailbox, bridge: dict[str, object]) -> dict[str, str]:
    return {
        "MAILBOX_ACCOUNT": mailbox.address, "MAILBOX_USERNAME": mailbox.address, "MAILBOX_PASSWORD": "unused",
        "MAILBOX_TLS": "ssl", "MAILBOX_IMAP_PORT": str(bridge["imap_port"]),
        "MAILBOX_SMTP_PORT": str(bridge["smtp_port"]), "MAILBOX_CA_CERT_PATH": str(bridge["cert"]),
    }


async def test_app_connects_over_stdio_and_reads_mailbox_info(mailbox: Mailbox, bridge: dict[str, object]):
    environment = plugin_environment(mailbox, bridge)
    for name, value in environment.items():
        os.environ[f"PROTON_TEST_{name}"] = value
    config = PluginConfig(
        id="proton",
        transport=StdioTransport(
            type="stdio", command=sys.executable, args=["-m", "proton_plugin.server"],
            env_from={name: f"PROTON_TEST_{name}" for name in environment},
        ),
    )
    registry = PluginRegistry()
    await registry.connect_all([config])
    try:
        state = registry.states["proton"]
        assert state.status == "connected", state.reason
        assert state.info is not None and state.info.plugin_name == "proton"
        assert state.info.account == mailbox.address
    finally:
        await registry.close()


@pytest.fixture
def http_plugin(mailbox: Mailbox, bridge: dict[str, object]) -> Iterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = {
        **os.environ, **plugin_environment(mailbox, bridge),
        "MAILBOX_HTTP_HOST": "127.0.0.1", "MAILBOX_HTTP_PORT": str(port), "MAILBOX_HTTP_TOKEN": "plugin-test-token",
    }
    process = subprocess.Popen([sys.executable, "-m", "proton_plugin.server", "http"], env=environment)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        process.kill()
        process.wait(timeout=10)
        pytest.fail("Proton plugin did not start listening")
    yield f"http://127.0.0.1:{port}/mcp"
    process.terminate()
    process.wait(timeout=10)


@pytest.mark.parametrize(("token", "status"), [("plugin-test-token", "connected"), ("not-the-token", "failed")])
async def test_app_connects_over_http_only_with_the_bearer_token(
    http_plugin: str, monkeypatch: pytest.MonkeyPatch, token: str, status: str
):
    monkeypatch.setenv("PROTON_HTTP_TOKEN", token)
    config = PluginConfig(
        id="proton", transport=HttpTransport(type="http", url=http_plugin, bearer_token_env="PROTON_HTTP_TOKEN")
    )
    registry = PluginRegistry()
    await registry.connect_all([config])
    try:
        assert registry.states["proton"].status == status, registry.states["proton"].reason
    finally:
        await registry.close()


def test_settings_load_from_the_env_file_the_logon_task_points_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / "proton.env"
    env_file.write_text("MAILBOX_ACCOUNT=me@proton.me\nMAILBOX_USERNAME=me\nMAILBOX_PASSWORD=x\nMAILBOX_CA_CERT_PATH=/c.pem\nMAILBOX_IMAP_PORT=1144\n")
    monkeypatch.setenv("MAILBOX_ENV_FILE", str(env_file))

    settings = load_settings()

    assert settings.account == "me@proton.me" and settings.imap_port == 1144
