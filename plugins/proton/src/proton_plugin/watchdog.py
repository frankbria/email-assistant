"""Watchdog for the Bridge machine (spec §6.3): checks Bridge and the plugin every 60 s,
restarts whichever is down with backoff, stops on owner-only failures or after repeated
failed restarts, and serves a token-protected status the app reads when the plugin is down.

Run as its own always-on process: python -m proton_plugin.watchdog
"""

import hmac
import logging
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal

from pydantic import BaseModel

from proton_plugin.mailbox import ProtonMailbox
from proton_plugin.settings import ProtonSettings, load_settings

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60
# Wait after the 1st, 2nd, … failed restart. After the last one, restarts stop.
BACKOFF_SECONDS = (30, 60, 120, 300, 900)


class BridgeStatus(BaseModel):
    state: Literal["unknown", "ok", "restarting", "needs_owner"] = "unknown"
    detail: str = ""
    first_failing_layer: str | None = None
    restarts: int = 0
    failed_restarts: int = 0
    checks: int = 0


class PluginStatus(BaseModel):
    state: Literal["not_supervised", "running", "restarting", "needs_owner"] = "not_supervised"
    restarts: int = 0
    failed_restarts: int = 0


class WatchdogStatus(BaseModel):
    bridge: BridgeStatus
    plugin: PluginStatus
    checked_at: datetime | None = None


class Watchdog:
    def __init__(self, settings: ProtonSettings, plugin_command: list[str] | None) -> None:
        self.settings = settings
        self.mailbox = ProtonMailbox(settings)
        self.plugin_command = plugin_command
        self.plugin_process: subprocess.Popen[bytes] | None = None
        self.bridge = BridgeStatus()
        self.plugin = PluginStatus(state="not_supervised" if plugin_command is None else "restarting")
        self.checked_at: datetime | None = None
        self._next_restart_at = 0.0
        self._next_plugin_start_at = 0.0
        self._lock = threading.Lock()

    def status(self) -> dict[str, object]:
        with self._lock:
            return WatchdogStatus(bridge=self.bridge, plugin=self.plugin, checked_at=self.checked_at).model_dump(mode="json")

    def tick(self, now: float) -> None:
        """One round of checks. `now` is a monotonic time in seconds."""
        self._supervise_plugin(now)
        health = self.mailbox.health()
        failing = next((check for check in health.checks if not check.ok), None)
        with self._lock:
            self.checked_at = datetime.now(UTC)
            self.bridge.checks += 1
            if failing is None:
                self.bridge = self.bridge.model_copy(update={"state": "ok", "detail": "", "first_failing_layer": None, "failed_restarts": 0})
                self._next_restart_at = now
                return
            self.bridge.first_failing_layer = failing.layer
            if not health.repair_actions:
                # Owner-only (e.g. Bridge needs re-login), or no restart command configured.
                self.bridge.state, self.bridge.detail = "needs_owner", failing.detail
                return
            if now < self._next_restart_at:  # still within the last restart's wait
                self.bridge.state, self.bridge.detail = "restarting", failing.detail
                return
            if self.bridge.failed_restarts >= len(BACKOFF_SECONDS):
                self.bridge.state = "needs_owner"
                self.bridge.detail = (
                    f"Bridge didn't come back after {self.bridge.failed_restarts} restarts. {failing.detail}"
                )
                return
            self.bridge.state, self.bridge.detail = "restarting", failing.detail
            self.bridge.failed_restarts += 1
            self.bridge.restarts += 1
            self._next_restart_at = now + BACKOFF_SECONDS[self.bridge.failed_restarts - 1]
        self._restart_bridge()

    def _restart_bridge(self) -> None:
        command = self.settings.bridge_restart_command
        if not command:
            return
        try:
            # No output capture: Bridge started in the background would inherit our pipes.
            subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except (OSError, subprocess.SubprocessError) as error:
            with self._lock:
                self.bridge.detail = f"Restarting Bridge failed: {error}"

    def _supervise_plugin(self, now: float) -> None:
        """Start the plugin, and restart it with the same backoff as Bridge when it dies."""
        if self.plugin_command is None:
            return
        with self._lock:
            process = self.plugin_process
            if process is not None and process.poll() is None:
                # Alive at a check after its start: running, and its failure count resets.
                self.plugin.state, self.plugin.failed_restarts = "running", 0
                return
            if process is not None and now < self._next_plugin_start_at:
                self.plugin.state = "restarting"
                return
            if process is not None and self.plugin.failed_restarts >= len(BACKOFF_SECONDS):
                self.plugin.state = "needs_owner"
                return
            if process is not None:
                self.plugin.restarts += 1
                self.plugin.failed_restarts += 1
                self._next_plugin_start_at = now + BACKOFF_SECONDS[self.plugin.failed_restarts - 1]
            self.plugin.state = "restarting"  # until a later check sees it alive
            try:
                self.plugin_process = subprocess.Popen(self.plugin_command)
            except OSError:
                self.plugin_process = None
                self.plugin.state = "needs_owner"

    def stop(self) -> None:
        process = self.plugin_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def serve_status(watchdog: Watchdog, host: str, port: int, token: str) -> ThreadingHTTPServer:
    """Serve GET /status (JSON) to callers presenting `Authorization: Bearer <token>`."""
    expected = f"Bearer {token}".encode()

    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            supplied = (self.headers.get("Authorization") or "").encode()
            if not hmac.compare_digest(supplied, expected):
                self.send_response(401)
                self.send_header("WWW-Authenticate", "Bearer")
                self.end_headers()
                return
            if self.path != "/status":
                self.send_response(404)
                self.end_headers()
                return
            body = WatchdogStatus.model_validate(watchdog.status()).model_dump_json().encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # status polls aren't news
            pass

    server = ThreadingHTTPServer((host, port), StatusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    settings = load_settings()
    if not settings.watchdog_token:
        raise SystemExit("The watchdog needs MAILBOX_WATCHDOG_TOKEN for its status endpoint.")
    plugin_command = [sys.executable, "-m", "proton_plugin.server", "http"] if settings.http_host else None
    watchdog = Watchdog(settings, plugin_command=plugin_command)
    serve_status(watchdog, settings.http_host or "127.0.0.1", settings.watchdog_port, settings.watchdog_token)
    try:
        while True:
            try:
                watchdog.tick(time.monotonic())
            except Exception:  # the watchdog is the last line of defence: never die
                logger.exception("Watchdog check failed; trying again next interval")
            time.sleep(CHECK_INTERVAL_SECONDS)
    finally:
        watchdog.stop()


if __name__ == "__main__":
    main()
