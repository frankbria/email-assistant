# Proton layered health and repair (#47). "Bridge" is a real TLS front-end (pinned
# certificate) over GreenMail with authentication on (docker-compose.test.yml).
import imaplib
import os
import signal
import socket
import sys
import time
from pathlib import Path

import pytest
from imap_mailbox.mailbox import MailboxError
from imap_mailbox.server import build_server
from mailbox_contract import ErrorCode, Health
from mcp import Client
from proton_plugin.mailbox import ProtonMailbox
from proton_plugin.settings import ProtonSettings

from tests.utils.mail_server import MAIL_HOST, wait_until_ready
from tests.utils.tls_relay import start_tls_relay, write_certificate

AUTH_IMAP_PORT = int(os.environ.get("MAIL_AUTH_TEST_IMAP_PORT", "3144"))
AUTH_SMTP_PORT = int(os.environ.get("MAIL_AUTH_TEST_SMTP_PORT", "3026"))
USERNAME, SECRET = "bridge", "test"  # the one account on greenmail-auth
WRONG_SECRET = "nope"
LAYERS = ["plugin", "imap_port", "imap_login", "smtp_auth", "folders"]


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]  # nothing listens once the probe closes


@pytest.fixture(scope="module")
def bridge(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    wait_until_ready()
    wait_until_ready(imap_port=AUTH_IMAP_PORT, smtp_port=AUTH_SMTP_PORT)
    cert, key = write_certificate(tmp_path_factory.mktemp("bridge-auth"), "bridge")
    connection = imaplib.IMAP4(MAIL_HOST, AUTH_IMAP_PORT)
    connection.login(USERNAME, SECRET)
    for folder in ("Archive", "Sent"):
        connection.create(folder)
    connection.logout()
    return {
        "cert": str(cert),
        "imap_port": start_tls_relay(AUTH_IMAP_PORT, cert, key),
        "smtp_port": start_tls_relay(AUTH_SMTP_PORT, cert, key),
    }


def plugin(bridge: dict[str, object], **overrides: object) -> ProtonMailbox:
    settings: dict[str, object] = {
        "account": "bridge@test.example",
        "username": USERNAME,
        "password": SECRET,
        "tls": "ssl",
        "ca_cert_path": bridge["cert"],
        "imap_port": bridge["imap_port"],
        "smtp_port": bridge["smtp_port"],
    }
    return ProtonMailbox(ProtonSettings(**{**settings, **overrides}))


def first_failure(health: Health) -> str | None:
    return next((check.layer for check in health.checks if not check.ok), None)


def test_healthy_bridge_passes_every_layer_in_order(bridge):
    health = plugin(bridge).health()

    assert [check.layer for check in health.checks] == LAYERS
    assert health.status == "ok" and first_failure(health) is None and health.repair_actions == []


def test_bridge_stopped_fails_at_the_imap_port(bridge):
    health = plugin(bridge, imap_port=closed_port(), bridge_restart_command=["true"]).health()

    assert first_failure(health) == "imap_port" and health.status == "down"
    assert "isn't running" in health.checks[1].detail
    assert health.repair_actions == ["restart_bridge"]


def test_wrong_password_fails_at_login_and_needs_the_owner(bridge):
    health = plugin(bridge, password=WRONG_SECRET, bridge_restart_command=["true"]).health()

    assert first_failure(health) == "imap_login" and health.status == "down"
    assert "mailbox password" in health.checks[2].detail
    assert health.repair_actions == []  # a restart can't fix credentials


def test_smtp_blocked_fails_at_smtp_auth(bridge):
    health = plugin(bridge, smtp_port=closed_port(), bridge_restart_command=["true"]).health()

    assert first_failure(health) == "smtp_auth" and health.status == "degraded"
    assert health.repair_actions == ["restart_bridge"]


def test_no_restart_command_means_no_repair_offered(bridge):
    health = plugin(bridge, imap_port=closed_port()).health()

    assert first_failure(health) == "imap_port" and health.repair_actions == []


def test_repair_refuses_an_action_that_is_not_offered(bridge):
    with pytest.raises(MailboxError) as refused:
        plugin(bridge, bridge_restart_command=["true"]).repair("delete_everything")

    assert refused.value.code == ErrorCode.UNSUPPORTED


def test_repair_stops_early_when_a_restart_cannot_help(bridge, tmp_path: Path):
    # Bridge is down (restartable). The "restart" brings up something on the port that drops
    # every TLS handshake: answering, but broken in a way another restart can't fix.
    port, pid_file = closed_port(), tmp_path / "listener.pid"
    listener = (
        "import os, socket\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"server = socket.create_server(('127.0.0.1', {port}))\n"
        "while True:\n    server.accept()[0].close()\n"
    )
    starter = f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {listener!r}], start_new_session=True)"
    down = plugin(bridge, imap_port=port, bridge_restart_command=[sys.executable, "-c", starter], repair_wait_seconds=30)
    started = time.monotonic()
    try:
        result = down.repair("restart_bridge")
    finally:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if pid_file.exists():
            os.kill(int(pid_file.read_text()), signal.SIGTERM)

    assert not result.ok and "needs your attention" in result.detail
    assert time.monotonic() - started < 25  # stopped early, not after the full wait


def test_repair_runs_the_configured_restart_and_rechecks(bridge, tmp_path: Path):
    marker = tmp_path / "restarted"
    command = [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]
    stopped = plugin(bridge, imap_port=closed_port(), bridge_restart_command=command, repair_wait_seconds=1)

    result = stopped.repair("restart_bridge")

    assert marker.exists()  # the configured command ran
    assert not result.ok and "still isn't answering" in result.detail  # nothing really came back


async def test_repair_is_exposed_only_with_a_restart_command(bridge):
    for command, expected in ((["true"], True), (None, False)):
        mailbox = plugin(bridge, bridge_restart_command=command)
        async with Client(build_server(mailbox)) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
        assert ("repair" in names) is expected
        assert ("repair" in mailbox.mailbox_info().capabilities) is expected
