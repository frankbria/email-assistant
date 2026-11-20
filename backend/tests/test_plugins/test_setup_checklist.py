# Guided Proton setup checklist (#53, spec §6.2): each step goes green or shows its fix,
# from the plugin's layered health. The real Proton plugin runs over stdio against a TLS
# front-end over GreenMail with authentication on; "stopped Bridge" is a closed port that
# the front-end later starts listening on.
import imaplib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mailbox_contract import Folders, Health, HealthCheck, MailboxInfo
from proton_plugin.settings import ProtonSettings
from proton_plugin.watchdog import Watchdog, serve_status

from app.main import app
from app.plugins.config import PluginConfig, StdioTransport, WatchdogConfig
from app.plugins.diagnosis import WatchdogReport
from app.plugins.setup import build_checklist
from app.plugins.state import PluginState
from tests.plugins.test_proton_health import AUTH_IMAP_PORT, AUTH_SMTP_PORT, SECRET, USERNAME, closed_port
from tests.test_plugins.test_diagnosis import TOKEN, TOKEN_ENV, free_port
from tests.utils.auth import bearer_headers
from tests.utils.mail_server import MAIL_HOST, wait_until_ready
from tests.utils.tls_relay import fake_bridge, start_tls_relay, write_certificate

STEP_TITLES = [
    "Install Proton Mail Bridge and start it",
    "Sign in to Bridge",
    "Copy Bridge's IMAP and SMTP settings and password into the plugin settings",
    "Install the plugin and the watchdog",
    "Test the connection",
]


HEALTHY_WATCHDOG = WatchdogReport(bridge_state="up", bridge_detail="", bridge_layer=None, bridge_restarts=0, plugin_state="up")


def proton_config(watchdog: WatchdogConfig | None = None) -> PluginConfig:
    return PluginConfig(id="proton", transport=StdioTransport(type="stdio", command="proton"), watchdog=watchdog)


# The plugin reads its settings from MAILBOX_ENV_FILE, as on the Bridge machine.
PROTON_ENTRY = f"""
plugins:
  - id: proton
    transport:
      type: stdio
      command: {sys.executable}
      args: [-m, proton_plugin.server]
      env_from:
        MAILBOX_ENV_FILE: SETUP_PLUGIN_SETTINGS_FILE
    watchdog:
      url: http://127.0.0.1:{{watchdog_port}}/status
      token_env: {TOKEN_ENV}
      machine: DESKTOP-BRIDGE
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
        "account": "bridge@test.example",
        "username": USERNAME,
        "tls": "ssl",
        "ca_cert_path": str(cert),
        "imap_port": imap_port,
        "smtp_port": smtp_port,
        "password": SECRET,
    }
    settings_file = tmp_path / "proton.env"
    settings_file.write_text("".join(f"MAILBOX_{name.upper()}={value}\n" for name, value in settings.items()))
    monkeypatch.setenv("SETUP_PLUGIN_SETTINGS_FILE", str(settings_file))
    watchdog_port = free_port()
    watchdog = serve_status(
        Watchdog(ProtonSettings(_env_file=settings_file), plugin_command=None),  # type: ignore[call-arg]  # fields come from the file
        host="127.0.0.1",
        port=watchdog_port,
        token=TOKEN,
    )
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    config = tmp_path / "plugins.yaml"
    config.write_text(PROTON_ENTRY.format(watchdog_port=watchdog_port))
    monkeypatch.setenv("PLUGINS_CONFIG", str(config))

    def start() -> None:
        start_tls_relay(AUTH_IMAP_PORT, cert, key, listen_port=imap_port)

    yield start
    watchdog.shutdown()


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
    state = PluginState(id="proton", status="failed", reason="Could not connect: no such file")

    checklist = build_checklist(proton_config(), state, None, None)

    statuses = [step.status for step in checklist.steps]
    assert statuses == ["waiting", "waiting", "waiting", "failing", "waiting"]
    assert "Could not connect: no such file" in (checklist.steps[3].detail or "")


def test_a_rejected_login_fails_the_sign_in_step_with_the_plugins_words():
    health = Health(
        status="down",
        repair_actions=[],
        checks=[
            HealthCheck(layer="plugin", ok=True, detail="The plugin is answering."),
            HealthCheck(layer="imap_port", ok=True, detail="Bridge is listening."),
            HealthCheck(layer="imap_login", ok=False, detail="Bridge rejected the login."),
        ],
    )
    config = proton_config(WatchdogConfig(url="http://127.0.0.1:1/status", token_env=TOKEN_ENV, machine="DESKTOP-BRIDGE"))

    checklist = build_checklist(config, PluginState(id="proton", status="connected"), health, HEALTHY_WATCHDOG)

    assert [step.status for step in checklist.steps] == ["done", "failing", "waiting", "done", "waiting"]
    assert checklist.steps[1].detail is not None and "Bridge rejected the login." in checklist.steps[1].detail


def test_requires_the_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUGINS_CONFIG", str(tmp_path / "none.yaml"))

    with TestClient(app) as client:
        assert client.post("/api/v1/connections/proton/check").status_code == 401


def test_a_connected_plugin_without_a_watchdog_in_plugins_yaml_fails_the_install_step():
    checklist = build_checklist(proton_config(), PluginState(id="proton", status="connected"), None, None)

    install_step = checklist.steps[3]
    assert install_step.status == "failing"
    assert install_step.detail is not None and "no watchdog" in install_step.detail


def test_proton_keeps_its_title_and_has_no_warnings():
    checklist = build_checklist(proton_config(), PluginState(id="proton", status="connected"), None, None)

    assert checklist.title == "Set up Proton Mail" and checklist.warnings == []


# --- Gmail (#97) ---------------------------------------------------------------------------

GMAIL_STEP_TITLES = [
    "Turn on 2-Step Verification for the Google account",
    "Create an app password and set it as GMAIL_APP_PASSWORD",
    "Check that IMAP is on in Gmail's settings",
    "Add the Gmail plugin to plugins.yaml",
    "Test the connection",
]
GMAIL_INFO = MailboxInfo(
    contract_version="1.0",
    plugin_name="gmail",
    plugin_version="0.1.0",
    account="owner@example.com",
    folders=Folders(inbox="INBOX", archive="[Gmail]/All Mail", sent="[Gmail]/Sent Mail"),
    capabilities=[],
)


def gmail_state() -> PluginState:
    return PluginState(id="gmail", status="connected", info=GMAIL_INFO)


def gmail_config() -> PluginConfig:
    return PluginConfig(id="gmail", transport=StdioTransport(type="stdio", command="gmail"))


def test_a_rejected_gmail_login_points_at_each_sign_in_step_once_with_gmails_words():
    rejected = "Gmail rejected the IMAP login."
    health = Health(
        status="degraded",
        repair_actions=[],
        checks=[
            HealthCheck(layer="imap_login", ok=False, detail=rejected),
            HealthCheck(layer="smtp", ok=True, detail="ok"),
        ],
    )

    checklist = build_checklist(gmail_config(), gmail_state(), health, None)

    assert checklist.title == "Set up Gmail"
    assert [step.title for step in checklist.steps] == GMAIL_STEP_TITLES
    assert [step.status for step in checklist.steps] == ["failing", "failing", "failing", "done", "done"]
    details = [step.detail or "" for step in checklist.steps[:3]]
    assert rejected in details[0] and not [detail for detail in details[1:] if rejected in detail]
    assert "2-Step Verification" in details[0] and "IMAP" in details[2]
    assert "apppasswords" in details[1]


def test_a_gmail_plugin_that_never_started_still_gets_gmail_steps_with_its_step_failing():
    """No app password set, say: the plugin never answered, so its command says it is Gmail."""
    never_started = PluginState(id="gmail", status="failed", reason="Could not connect: no such file")

    checklist = build_checklist(gmail_config(), never_started, None, None)

    assert checklist.title == "Set up Gmail"
    assert [step.status for step in checklist.steps] == ["waiting", "waiting", "waiting", "failing", "waiting"]
    assert "Could not connect: no such file" in (checklist.steps[3].detail or "")


def test_warnings_are_shown_alongside_the_steps():
    warnings = ["Gmail's Auto-Expunge is on."]

    checklist = build_checklist(gmail_config(), gmail_state(), None, None, warnings)

    assert checklist.warnings == warnings


GMAIL_ENTRY = f"""
plugins:
  - id: gmail
    transport:
      type: stdio
      command: {sys.executable}
      args: [-m, gmail_plugin.server]
      env_from:
{{env_from}}
"""


def gmail_plugins_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: dict[str, str]) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(f"GMAIL_SETUP_{name}", value)
    env_from = "".join(f"        {name}: GMAIL_SETUP_{name}\n" for name in environment)
    config = tmp_path / "plugins.yaml"
    config.write_text(GMAIL_ENTRY.format(env_from=env_from))
    monkeypatch.setenv("PLUGINS_CONFIG", str(config))


def test_gmail_with_auto_expunge_off_goes_green_without_a_warning(tmp_path, monkeypatch, mailbox):
    """AC (off half, on GreenMail, which never auto-expunges): the real plugin over stdio."""
    mailbox.create_folder('"[Gmail]/Trash"')
    bridge = fake_bridge()
    gmail_plugins_yaml(
        tmp_path,
        monkeypatch,
        {
            "MAILBOX_ACCOUNT": mailbox.address,
            "MAILBOX_PASSWORD": "unused",
            "MAILBOX_IMAP_HOST": "127.0.0.1",
            "MAILBOX_IMAP_PORT": str(bridge.imap_port),
            "MAILBOX_SMTP_HOST": "127.0.0.1",
            "MAILBOX_SMTP_PORT": str(bridge.smtp_port),
            "MAILBOX_CA_CERT_PATH": str(bridge.cert),
        },
    )

    with TestClient(app, headers=bearer_headers()) as client:
        checklist = client.post("/api/v1/connections/gmail/check").json()

    assert checklist["title"] == "Set up Gmail"
    assert [step["status"] for step in checklist["steps"]] == ["done"] * 5
    assert checklist["warnings"] == []


def test_a_watchdog_that_does_not_answer_fails_the_install_step_naming_its_machine():
    config = proton_config(WatchdogConfig(url="http://127.0.0.1:1/status", token_env=TOKEN_ENV, machine="DESKTOP-BRIDGE"))

    checklist = build_checklist(config, PluginState(id="proton", status="connected"), None, "refused")

    install_step = checklist.steps[3]
    assert install_step.status == "failing"
    assert install_step.detail is not None and "DESKTOP-BRIDGE" in install_step.detail and "isn't running" in install_step.detail
