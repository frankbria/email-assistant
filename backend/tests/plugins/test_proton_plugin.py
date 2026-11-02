# Proton plugin skeleton (#43). Bridge is stood in for by a real TLS front-end (a
# generated certificate valid for 127.0.0.1) relaying to the GreenMail test server.
import datetime
import ipaddress
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID
from pydantic import ValidationError

from app.plugins.config import HttpTransport, PluginConfig, StdioTransport
from app.plugins.registry import PluginRegistry
from proton_plugin.mailbox import ProtonMailbox
from proton_plugin.mutf7 import decode_mutf7
from proton_plugin.settings import ProtonSettings
from tests.utils.mail_server import IMAP_PORT, SMTP_PORT, Mailbox


def write_certificate(directory: Path, name: str) -> tuple[Path, Path]:
    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, None)  # Ed25519 signs without a separate hash
    )
    cert_path, key_path = directory / f"{name}.pem", directory / f"{name}.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


def start_tls_relay(target_port: int, cert_path: Path, key_path: Path) -> int:
    """Implicit-TLS front-end on a random port, forwarding plaintext to target_port."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    listener = socket.create_server(("127.0.0.1", 0))

    def pipe(source: socket.socket, sink: socket.socket) -> None:
        try:
            while data := source.recv(65536):
                sink.sendall(data)
        except OSError:
            pass
        finally:
            for end in (source, sink):
                end.close()

    def handle(client: socket.socket) -> None:
        try:
            secure = context.wrap_socket(client, server_side=True)
        except (ssl.SSLError, OSError):
            client.close()
            return
        upstream = socket.create_connection(("127.0.0.1", target_port))
        threading.Thread(target=pipe, args=(secure, upstream), daemon=True).start()
        pipe(upstream, secure)

    def serve() -> None:
        while True:
            client, _ = listener.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


@pytest.fixture(scope="module")
def bridge(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    directory = tmp_path_factory.mktemp("bridge")
    cert_path, key_path = write_certificate(directory, "bridge")
    wrong_cert_path, _ = write_certificate(directory, "some-other-bridge")
    return {
        "cert": cert_path,
        "wrong_cert": wrong_cert_path,
        "imap_port": start_tls_relay(IMAP_PORT, cert_path, key_path),
        "smtp_port": start_tls_relay(SMTP_PORT, cert_path, key_path),
    }


def proton_settings(mailbox: Mailbox, bridge: dict[str, object], cert: str = "cert") -> ProtonSettings:
    return ProtonSettings(
        account=mailbox.address, username=mailbox.address, password="unused", tls="ssl",
        imap_port=bridge["imap_port"], smtp_port=bridge["smtp_port"], smtp_login=False,
        ca_cert_path=str(bridge[cert]),
    )


@pytest.mark.parametrize(
    ("encoded", "decoded"),
    [("Folders/&AOk-t&AOk-", "Folders/été"), ("Labels/&ZeVnLIqe-", "Labels/日本語"), ("R&-D", "R&D"), ("INBOX", "INBOX")],
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


def test_http_mode_refuses_all_interfaces():
    with pytest.raises(ValidationError, match="Tailscale"):
        ProtonSettings(**MINIMAL_SETTINGS, http_host="0.0.0.0")


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
    for folder in ("Archive", "Folders/&AOk-t&AOk-", "Labels/&ZeVnLIqe-"):
        mailbox.append(folder, sender="setup@example.com", subject="x", body="x")

    folders = ProtonMailbox(proton_settings(mailbox, bridge)).folder_map()

    assert "Archive" in folders["system"] and "INBOX" in folders["system"]
    assert folders["folders"] == ["été"] and folders["labels"] == ["日本語"]


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
