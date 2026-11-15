# Proton watchdog (#48). Bridge is a real process (TLS relays to the auth-enabled
# GreenMail) that the restart command really starts; the plugin is the real plugin process.
# tick(now) takes the time so the 60 s cadence and backoff are tested without waiting.
import json
import os
import signal
import socket
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from urllib.error import HTTPError

import pytest

from proton_plugin.settings import ProtonSettings
from proton_plugin.watchdog import BACKOFF_SECONDS, LOGIN_GRACE_SECONDS, Watchdog, serve_status
from tests.utils.mail_server import wait_until_ready
from tests.utils.tls_relay import write_certificate

FAKE_BRIDGE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_bridge_process.py"
AUTH_IMAP_PORT = int(os.environ.get("MAIL_AUTH_TEST_IMAP_PORT", "3144"))
AUTH_SMTP_PORT = int(os.environ.get("MAIL_AUTH_TEST_SMTP_PORT", "3026"))
WRONG_SECRET = "nope"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for(condition, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.1)


@pytest.fixture
def bridge_layout(tmp_path: Path) -> Iterator[dict[str, object]]:
    wait_until_ready(imap_port=AUTH_IMAP_PORT, smtp_port=AUTH_SMTP_PORT)
    cert, key = write_certificate(tmp_path, "bridge")
    layout = {
        "cert": cert, "key": key, "imap_port": free_port(), "smtp_port": free_port(),
        "pid_file": tmp_path / "bridge.pid",
    }
    yield layout
    if Path(layout["pid_file"]).exists():
        os.kill(int(Path(layout["pid_file"]).read_text()), signal.SIGTERM)


def start_bridge_command(layout: dict[str, object]) -> list[str]:
    """What the owner would configure: start Bridge in the background and return."""
    argv = [sys.executable, str(FAKE_BRIDGE), str(layout["cert"]), str(layout["key"]),
            str(layout["imap_port"]), str(layout["smtp_port"]), str(layout["pid_file"])]
    return [sys.executable, "-c", f"import subprocess; subprocess.Popen({argv!r}, start_new_session=True)"]


def settings(layout: dict[str, object], **overrides: object) -> ProtonSettings:
    values: dict[str, object] = {
        "account": "bridge@test.example", "username": "bridge", "password": "test", "tls": "ssl",
        "ca_cert_path": str(layout["cert"]), "imap_port": layout["imap_port"], "smtp_port": layout["smtp_port"],
        "bridge_restart_command": start_bridge_command(layout), "folder_archive": "INBOX", "folder_sent": "INBOX",
    }
    return ProtonSettings(**{**values, **overrides})


def test_stopped_bridge_is_restarted_on_the_next_check(bridge_layout):
    """AC-P.1: Bridge stopped → the next check restarts it with no owner action."""
    watchdog = Watchdog(settings(bridge_layout), plugin_command=None)

    watchdog.tick(now=0)
    wait_for(Path(bridge_layout["pid_file"]).exists)
    wait_for(lambda: watchdog.tick(now=60) or watchdog.status()["bridge"]["state"] == "ok")

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
    wait_for(Path(bridge_layout["pid_file"]).exists)
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
    layout = {"cert": cert, "key": cert, "pid_file": tmp_path / "unused.pid", "imap_port": free_port(), "smtp_port": free_port()}
    watchdog = Watchdog(settings(layout, bridge_restart_command=command), plugin_command=None)

    restart_times = []
    for now in range(0, 3600, 10):
        before = len(list(marker_dir.iterdir()))
        watchdog.tick(now=now)
        if len(list(marker_dir.iterdir())) > before:
            restart_times.append(now)

    gaps = [later - earlier for earlier, later in zip(restart_times, restart_times[1:])]
    assert gaps == [round_up(seconds) for seconds in BACKOFF_SECONDS[:-1]]
    assert len(restart_times) == len(BACKOFF_SECONDS)
    assert watchdog.status()["bridge"]["state"] == "needs_owner"


def round_up(seconds: int) -> int:
    return -(-seconds // 10) * 10  # ticks are 10 s apart in the test


def test_status_endpoint_requires_the_token(bridge_layout):
    watchdog = Watchdog(settings(bridge_layout), plugin_command=None)
    port = free_port()
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

    gaps = [later - earlier for earlier, later in zip(starts[1:], starts[2:])]
    assert gaps == [round_up(seconds) for seconds in BACKOFF_SECONDS[:-1]]
    assert watchdog.status()["plugin"]["state"] == "needs_owner"


def test_a_rejected_login_is_retried_with_backoff_before_it_needs_the_owner(bridge_layout):
    """Bridge opens its port before it has loaded the account and rejects logins until then
    ("no such user"): retry with growing gaps for the grace period, then ask the owner."""
    Watchdog(settings(bridge_layout), plugin_command=None).tick(now=0)  # starts Bridge
    wait_for(Path(bridge_layout["pid_file"]).exists)
    rejecting = Watchdog(settings(bridge_layout, password=WRONG_SECRET), plugin_command=None)
    wait_for(lambda: rejecting.mailbox.health().checks[-1].layer == "imap_login")

    now, delays = 0.0, []
    while now < LOGIN_GRACE_SECONDS:
        delays.append(rejecting.tick(now=now))
        assert rejecting.status()["bridge"]["state"] == "restarting"
        now += delays[-1]
    rejecting.tick(now=now)

    assert delays == sorted(delays) and delays[0] < delays[-1] <= 60
    assert sum(delays) >= 120
    status = rejecting.status()["bridge"]
    assert status["state"] == "needs_owner" and status["restarts"] == 0


def test_a_companion_service_is_started_only_while_its_port_is_down(tmp_path: Path):
    """The gateway/adapter on this machine: started when nothing answers on its port."""
    port, starts, pid_file = free_port(), tmp_path / "starts", tmp_path / "companion.pid"
    serve = (
        f"import http.server, os, pathlib; pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        f"http.server.HTTPServer(('127.0.0.1', {port}), http.server.BaseHTTPRequestHandler).serve_forever()"
    )
    start = (
        f"import pathlib, subprocess, sys; open({str(starts)!r}, 'a').write('x'); "
        f"subprocess.Popen([sys.executable, '-c', {serve!r}], start_new_session=True)"
    )
    cert, _ = write_certificate(tmp_path, "bridge")
    layout = {"cert": cert, "key": cert, "pid_file": tmp_path / "unused.pid", "imap_port": free_port(), "smtp_port": free_port()}
    watchdog = Watchdog(
        settings(layout, bridge_restart_command=None, companion_start_commands={port: [sys.executable, "-c", start]}),
        plugin_command=None,
    )
    try:
        watchdog.tick(now=0)
        wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0)
        watchdog.tick(now=60)

        assert starts.read_text() == "x"
    finally:
        if pid_file.exists():
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
