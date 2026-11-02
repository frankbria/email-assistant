# Guided Proton setup checklist (#53, spec §6.2): each step goes green or shows its fix,
# from the plugin's layered health. The real Proton plugin runs over stdio against a TLS
# front-end over GreenMail with authentication on; "stopped Bridge" is a closed port that
# the front-end later starts listening on.
import imaplib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.setup import build_checklist
from app.plugins.state import PluginState
from mailbox_contract import Health, HealthCheck
from tests.plugins.test_proton_health import AUTH_IMAP_PORT, AUTH_SMTP_PORT, SECRET, USERNAME, closed_port
from tests.utils.auth import bearer_headers
from tests.utils.mail_server import MAIL_HOST, wait_until_ready
from tests.utils.tls_relay import start_tls_relay, write_certificate

STEP_TITLES = [
    "Install Proton Mail Bridge and start it",
    "Sign in to Bridge",
    "Copy Bridge's IMAP and SMTP settings and password into the plugin settings",
    "Install the plugin and the watchdog",
    "Test the connection",
]


PROTON_ENTRY = f"""
plugins:
  - id: proton
    transport:
      type: stdio
      command: {sys.executable}
      args: [-m, proton_plugin.server]
      env_from:
        MAILBOX_ACCOUNT: SETUP_ACCOUNT
        MAILBOX_USERNAME: SETUP_USER
        MAILBOX_PASSWORD: SETUP_BPW
        MAILBOX_TLS: SETUP_TLS
        MAILBOX_CA_CERT_PATH: SETUP_CERT
        MAILBOX_IMAP_PORT: SETUP_IMAP_PORT
        MAILBOX_SMTP_PORT: SETUP_SMTP_PORT
"""


@pytest.fixture
def stopped_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wait_until_ready(imap_port=AUTH_IMAP_PORT, smtp_port=AUTH_SMTP_PORT)
    cert, key = write_certificate(tmp_path, "bridge")
    connection = imaplib.IMAP4(MAIL_HOST, AUTH_IMAP_PORT)
    connection.login(USERNAME, SECRET)
    for folder in ("Archive", "Sent"):
        connection.create(folder)  # NO if it exists already; either way it's there
    connection.logout()
    imap_port = closed_port()
    smtp_port = start_tls_relay(AUTH_SMTP_PORT, cert, key)
    settings = {
        "SETUP_ACCOUNT": "bridge@test.example", "SETUP_USER": USERNAME, "SETUP_BPW": SECRET,
        "SETUP_TLS": "ssl", "SETUP_CERT": str(cert),
        "SETUP_IMAP_PORT": str(imap_port), "SETUP_SMTP_PORT": str(smtp_port),
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    config = tmp_path / "plugins.yaml"
    config.write_text(PROTON_ENTRY)
    monkeypatch.setenv("PLUGINS_CONFIG", str(config))

    def start() -> None:
        start_tls_relay(AUTH_IMAP_PORT, cert, key, listen_port=imap_port)

    return start


def test_stopped_bridge_shows_its_step_red_then_every_step_green_once_started(stopped_bridge):
    """AC: walking the checklist against a stopped Bridge shows the Bridge step red with its
    fix; after starting it, all steps go green."""
    with TestClient(app, headers=bearer_headers()) as client:
        stopped = client.post("/api/v1/connections/proton/check").json()

        stopped_bridge()
        started = client.post("/api/v1/connections/proton/check").json()

    assert [step["title"] for step in stopped["steps"]] == STEP_TITLES
    bridge_step = stopped["steps"][0]
    assert bridge_step["status"] == "failing"
    assert "Bridge isn't running" in bridge_step["detail"] and "Start Proton Mail Bridge" in bridge_step["detail"]
    assert [step["status"] for step in stopped["steps"][1:]] == ["waiting", "waiting", "done", "waiting"]
    assert [step["status"] for step in started["steps"]] == ["done"] * 5


def test_checking_an_unknown_plugin_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUGINS_CONFIG", str(tmp_path / "none.yaml"))

    with TestClient(app, headers=bearer_headers()) as client:
        assert client.post("/api/v1/connections/nope/check").status_code == 404


def test_a_plugin_that_is_not_answering_fails_its_step_and_the_bridge_steps_wait():
    config = PluginConfig(id="proton", transport=StdioTransport(type="stdio", command="/nonexistent/plugin"))
    state = PluginState(id="proton", status="failed", reason="Could not connect: no such file")

    checklist = build_checklist(config, state, None)

    statuses = [step.status for step in checklist.steps]
    assert statuses == ["waiting", "waiting", "waiting", "failing", "waiting"]
    assert "Could not connect: no such file" in (checklist.steps[3].detail or "")


def test_a_rejected_login_fails_the_sign_in_step_with_the_plugins_words():
    config = PluginConfig(id="proton", transport=StdioTransport(type="stdio", command="proton"))
    health = Health(status="down", repair_actions=[], checks=[
        HealthCheck(layer="plugin", ok=True, detail="The plugin is answering."),
        HealthCheck(layer="imap_port", ok=True, detail="Bridge is listening."),
        HealthCheck(layer="imap_login", ok=False, detail="Bridge rejected the login."),
    ])

    checklist = build_checklist(config, PluginState(id="proton", status="connected"), health)

    assert [step.status for step in checklist.steps] == ["done", "failing", "waiting", "done", "waiting"]
    assert checklist.steps[1].detail is not None and "Bridge rejected the login." in checklist.steps[1].detail


def test_requires_the_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUGINS_CONFIG", str(tmp_path / "none.yaml"))

    with TestClient(app) as client:
        assert client.post("/api/v1/connections/proton/check").status_code == 401

