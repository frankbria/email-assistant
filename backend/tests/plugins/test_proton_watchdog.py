# Proton watchdog (#48). Bridge is a real process (TLS relays to the auth-enabled
# GreenMail) that the restart command really starts; the plugin is the real plugin process.
# tick(now) takes the time so the 60 s cadence and backoff are tested without waiting.
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from itertools import pairwise
from pathlib import Path
from urllib.error import HTTPError

import pytest
from proton_plugin.settings import ProtonSettings
from proton_plugin.watchdog import BACKOFF_SECONDS, Watchdog, serve_status

from tests.utils.mail_server import wait_until_ready
from tests.utils.tls_relay import write_certificate

FAKE_BRIDGE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_bridge_process.py"
AUTH_IMAP_PORT = int(os.environ.get("MAIL_AUTH_TEST_IMAP_PORT", "3144"))
AUTH_SMTP_PORT = int(os.environ.get("MAIL_AUTH_TEST_SMTP_PORT", "3026"))
WRONG_SECRET = "nope"


def free_ports(count: int) -> list[int]:
    # Probes stay bound until all are chosen: one at a time, the OS can hand out the same port
    # twice, and a Bridge given one port for IMAP and SMTP dies binding the second.
    with ExitStack() as probes:
        sockets = [probes.enter_context(socket.socket()) for _ in range(count)]
        for probe in sockets:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in sockets]


def wait_for(condition: Callable[[], object], waiting_for: Callable[[], str], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, f"timed out waiting for {waiting_for()}"
        time.sleep(0.1)


def bridge_started(layout: dict[str, object]) -> str:
    log = Path(layout["bridge_log"])
    return f"the fake Bridge to write its pid file. Its log:\n{log.read_text() if log.exists() else '(not started)'}"


@pytest.fixture
def bridge_layout(tmp_path: Path) -> Iterator[dict[str, object]]:
    wait_until_ready(imap_port=AUTH_IMAP_PORT, smtp_port=AUTH_SMTP_PORT)
    cert, key = write_certificate(tmp_path, "bridge")
    imap_port, smtp_port = free_ports(2)
    layout = {
        "cert": cert,
        "key": key,
        "imap_port": imap_port,
        "smtp_port": smtp_port,
        "pid_file": tmp_path / "bridge.pid",
        "bridge_log": tmp_path / "bridge.log",
    }
    yield layout
    # Every Bridge the watchdog started, not just the one in the pid file: a restart can
    # outrun the pid file, or start a second Bridge that overwrites it.
    bridges_of_this_test = f"{FAKE_BRIDGE.name} {tmp_path}/"
    subprocess.run(["pkill", "-TERM", "-f", bridges_of_this_test], check=False)
    wait_for(lambda: not running_bridges(bridges_of_this_test), lambda: "this test's fake Bridges to stop")


def running_bridges(command_line_pattern: str) -> list[str]:
    # shortcut: needs pgrep/pkill (procps on Linux, built into macOS); use psutil if Windows runs these tests.
    found = subprocess.run(["pgrep", "-f", command_line_pattern], capture_output=True, text=True, check=False)
    return found.stdout.split()


def start_bridge_command(layout: dict[str, object]) -> list[str]:
    """What the owner would configure: start Bridge in the background and return."""
    argv = [
        sys.executable,
        str(FAKE_BRIDGE),
        str(layout["cert"]),
        str(layout["key"]),
        str(layout["imap_port"]),
        str(layout["smtp_port"]),
        str(layout["pid_file"]),
    ]
    log = str(layout["bridge_log"])
    starter = f"import subprocess; subprocess.Popen({argv!r}, start_new_session=True, stderr=open({log!r}, 'ab'))"
    return [sys.executable, "-c", starter]


def settings(layout: dict[str, object], **overrides: object) -> ProtonSettings:
    values: dict[str, object] = {
        "account": "bridge@test.example",
        "username": "bridge",
        "password": "test",
        "tls": "ssl",
        "ca_cert_path": str(layout["cert"]),
        "imap_port": layout["imap_port"],
        "smtp_port": layout["smtp_port"],
        "bridge_restart_command": start_bridge_command(layout),
        "folder_archive": "INBOX",
        "folder_sent": "INBOX",
    }
    return ProtonSettings(**{**values, **overrides})


def test_stopped_bridge_is_restarted_on_the_next_check(bridge_layout):
    """AC-P.1: Bridge stopped → the next check restarts it with no owner action."""
    watchdog = Watchdog(settings(bridge_layout), plugin_command=None)

    watchdog.tick(now=0)
    wait_for(Path(bridge_layout["pid_file"]).exists, lambda: bridge_started(bridge_layout))
    wait_for(
        lambda: watchdog.tick(now=60) or watchdog.status()["bridge"]["state"] == "ok",
        lambda: f"the restarted Bridge to check ok. Last status: {watchdog.status()['bridge']}",
    )

    status = watchdog.status()["bridge"]
    assert status["state"] == "ok" and status["restarts"] == 1


def test_killed_plugin_is_restarted(bridge_layout):
    """AC-P.2: the plugin process is killed → the watchdog starts it again."""
    plugin_command = [sys.executable, "-c", "import time; time.sleep(600)"]
    watchdog = Watchdog(settings(bridge_layout), plugin_command=plugin_command)
    try:
        watchdog.tick(now=0)
        first = watchdog.plugin_process
        assert first is not None and first.poll() is None
        first.kill()
        first.wait(timeout=10)

        watchdog.tick(now=60)
        assert watchdog.status()["plugin"]["state"] == "restarting"
        watchdog.tick(now=120)

        second = watchdog.plugin_process
        assert second is not None and second.poll() is None and second.pid != first.pid
        assert watchdog.status()["plugin"] == {"state": "running", "restarts": 1, "failed_restarts": 0}
    finally:
        watchdog.stop()


def test_owner_only_failure_stops_automatic_restarts(bridge_layout):
    """AC-P.4 (watchdog half): Bridge needs re-login → restarts stop; checks continue."""
    subprocess_command = start_bridge_command(bridge_layout)
    watchdog = Watchdog(settings(bridge_layout, bridge_restart_command=subprocess_command), plugin_command=None)
    watchdog.tick(now=0)  # Bridge down → restart (restartable)
    wait_for(Path(bridge_layout["pid_file"]).exists, lambda: bridge_started(bridge_layout))
    rejecting = Watchdog(settings(bridge_layout, password=WRONG_SECRET), plugin_command=None)

    for minute in range(5):
        rejecting.tick(now=60 * minute)

    status = rejecting.status()["bridge"]
    assert status["state"] == "needs_owner" and status["restarts"] == 0
    detail = status["detail"]
    assert "mailbox password" in detail
    assert status["checks"] == 5


def test_restarts_back_off_then_escalate(tmp_path: Path):
    marker_dir = tmp_path / "restarts"
    marker_dir.mkdir()
    # A "restart" that never brings Bridge back; each run leaves a marker.
    command = [sys.executable, "-c", f"import pathlib, time; pathlib.Path({str(marker_dir)!r}, str(time.time_ns())).touch()"]
    cert, _ = write_certificate(tmp_path, "bridge")
    imap_port, smtp_port = free_ports(2)
    layout = {
        "cert": cert,
        "key": cert,
        "pid_file": tmp_path / "unused.pid",
        "bridge_log": tmp_path / "unused.log",
        "imap_port": imap_port,
        "smtp_port": smtp_port,
    }
    watchdog = Watchdog(settings(layout, bridge_restart_command=command), plugin_command=None)

    restart_times = []
    for now in range(0, 3600, 10):
        before = len(list(marker_dir.iterdir()))
        watchdog.tick(now=now)
        if len(list(marker_dir.iterdir())) > before:
            restart_times.append(now)

    gaps = [later - earlier for earlier, later in pairwise(restart_times)]
    assert gaps == [round_up(seconds) for seconds in BACKOFF_SECONDS[:-1]]
    assert len(restart_times) == len(BACKOFF_SECONDS)
    assert watchdog.status()["bridge"]["state"] == "needs_owner"


def round_up(seconds: int) -> int:
    return -(-seconds // 10) * 10  # ticks are 10 s apart in the test


def test_status_endpoint_requires_the_token(bridge_layout):
    watchdog = Watchdog(settings(bridge_layout), plugin_command=None)
    (port,) = free_ports(1)
    server = serve_status(watchdog, host="127.0.0.1", port=port, token="watchdog-test-token")
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/status", headers={"Authorization": "Bearer watchdog-test-token"})
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.load(response)
        with pytest.raises(HTTPError) as refused:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=5)
    finally:
        server.shutdown()

    assert set(body) >= {"bridge", "plugin", "checked_at"}
    assert refused.value.code == 401


def test_crash_looping_plugin_backs_off_then_asks_for_the_owner(bridge_layout):
    # No Bridge restarts here: only the plugin supervision is under test.
    watchdog = Watchdog(settings(bridge_layout, bridge_restart_command=None), plugin_command=[sys.executable, "-c", "raise SystemExit(1)"])
    starts = []
    for now in range(0, 3600, 10):
        before = watchdog.plugin_process
        watchdog.tick(now=now)
        if watchdog.plugin_process is not before:
            starts.append(now)
        if watchdog.plugin_process is not None:
            watchdog.plugin_process.wait(timeout=10)

    gaps = [later - earlier for earlier, later in pairwise(starts[1:])]
    assert gaps == [round_up(seconds) for seconds in BACKOFF_SECONDS[:-1]]
    assert watchdog.status()["plugin"]["state"] == "needs_owner"
