# App-side connectivity diagnosis (#50): plugin health + the watchdog's /status → one
# plain-language state. Plugins and watchdogs are real processes/servers; "machine offline"
# uses an unroutable address, "waiting for login" a refused port.
import socket
from pathlib import Path

import pytest

from app.plugins.config import PluginConfig, StdioTransport, WatchdogConfig
from app.plugins.diagnosis import diagnose
from app.plugins.registry import PluginRegistry, PluginState
from proton_plugin.settings import ProtonSettings
from proton_plugin.watchdog import Watchdog, serve_status
from tests.utils.tls_relay import write_certificate

TOKEN_ENV = "DIAGNOSIS_TEST_WATCHDOG_TOKEN"
TOKEN = "diagnosis-test-token"
UNROUTABLE = "192.0.2.1"  # TEST-NET-1: never answers, like a machine that's off


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def failed_plugin(plugin_id: str = "proton") -> PluginState:
    return PluginState(id=plugin_id, status="failed", reason="Could not connect: connection refused")


def watchdog_config(host: str, port: int) -> WatchdogConfig:
    return WatchdogConfig(url=f"http://{host}:{port}/status", token_env=TOKEN_ENV, machine="DESKTOP-BRIDGE")


@pytest.fixture(autouse=True)
def watchdog_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, TOKEN)


@pytest.fixture
def running_watchdog(tmp_path: Path):
    cert, _ = write_certificate(tmp_path, "bridge")
    settings = ProtonSettings(
        account="a@b.c", username="a", password="x", ca_cert_path=str(cert),
        imap_port=free_port(), smtp_port=free_port(),
    )
    watchdog = Watchdog(settings, plugin_command=None)
    port = free_port()
    server = serve_status(watchdog, host="127.0.0.1", port=port, token=TOKEN)
    yield watchdog, port
    server.shutdown()


async def test_machine_offline_is_not_reported_as_bridge_down():
    """AC-P.3"""
    state = await diagnose(failed_plugin(), None, watchdog_config(UNROUTABLE, 8766), timeout=1)

    assert state.kind == "machine_offline"
    assert state.message == "DESKTOP-BRIDGE is offline."


async def test_machine_up_without_watchdog_is_waiting_for_login():
    """AC-P.5: the watchdog starts at logon; a refused connection means the machine is up."""
    state = await diagnose(failed_plugin(), None, watchdog_config("127.0.0.1", free_port()))

    assert state.kind == "waiting_for_login"
    assert state.message == "Waiting for login on DESKTOP-BRIDGE."


async def test_plugin_down_while_watchdog_restarts_it(running_watchdog):
    """AC-P.2"""
    watchdog, port = running_watchdog
    watchdog.plugin.state = "restarting"

    state = await diagnose(failed_plugin(), None, watchdog_config("127.0.0.1", port))

    assert state.kind == "plugin_restarting"
    assert state.message == "The proton plugin is down → restarting."


async def test_bridge_restarting_is_reported_from_the_watchdog(running_watchdog):
    watchdog, port = running_watchdog
    watchdog.tick(now=0)  # Bridge isn't listening → watchdog would restart it

    state = await diagnose(failed_plugin(), None, watchdog_config("127.0.0.1", port))

    assert state.kind in {"bridge_restarting", "owner_action"}
    assert "Bridge" in state.message


async def test_owner_only_failure_shows_the_exact_instruction(tmp_path: Path):
    """AC-P.4: the plugin answers, and its health says only the owner can fix it."""
    from mailbox_contract import Health, HealthCheck

    instruction = "Bridge rejected the IMAP login. Re-enter the mailbox password Bridge shows for this account."
    health = Health(
        status="down",
        checks=[HealthCheck(layer="plugin", ok=True, detail="ok"), HealthCheck(layer="imap_login", ok=False, detail=instruction)],
        repair_actions=[],
    )
    connected = PluginState(id="proton", status="connected")

    state = await diagnose(connected, health, None)

    assert state.kind == "owner_action" and state.message == instruction
    assert state.first_failing_layer == "imap_login"


async def test_healthy_plugin_after_a_watchdog_restart_says_bridge_restarted(running_watchdog):
    from mailbox_contract import Health, HealthCheck

    watchdog, port = running_watchdog
    watchdog.bridge.restarts = 1
    watchdog.bridge.state = "ok"
    healthy = Health(status="ok", checks=[HealthCheck(layer="plugin", ok=True, detail="ok")], repair_actions=[])

    state = await diagnose(PluginState(id="proton", status="connected"), healthy, watchdog_config("127.0.0.1", port))

    assert state.kind == "bridge_restarted" and state.message == "Bridge restarted. Mail is flowing again."


async def test_refresh_reconnects_a_failed_plugin_within_one_cycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """After the owner fixes things, the next refresh (≤ 60 s) reconnects and re-diagnoses."""
    import sys

    fake = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mailbox_plugin.py"
    command_file = tmp_path / "command"
    command_file.write_text("/nonexistent/plugin")  # broken until "fixed"
    config = PluginConfig(id="proton", transport=StdioTransport(type="stdio", command="/nonexistent/plugin"))
    registry = PluginRegistry()
    await registry.connect_all([config])
    try:
        assert registry.states["proton"].status == "failed"
        fixed = config.model_copy(update={"transport": StdioTransport(type="stdio", command=sys.executable, args=[str(fake)])})
        registry.configs["proton"] = fixed  # the owner fixed it

        await registry.refresh()

        assert registry.states["proton"].status == "connected"
        assert registry.diagnoses["proton"].kind == "ok"
    finally:
        await registry.close()
