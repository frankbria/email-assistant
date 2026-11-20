# backend/app/plugins/diagnosis.py
"""One plain-language connection state per plugin, from its `health` and (for plugins on
another machine) that machine's watchdog status endpoint (spec §6.3)."""

import os
from datetime import UTC, datetime
from typing import Literal

import httpx
from mailbox_contract import Health
from pydantic import BaseModel

from app.plugins.config import WatchdogConfig
from app.plugins.state import PluginState

Kind = Literal[
    "ok",
    "bridge_restarted",
    "bridge_restarting",
    "plugin_restarting",
    "plugin_failed",
    "owner_action",
    "machine_offline",
    "waiting_for_login",
]


class ConnectionState(BaseModel):
    plugin_id: str
    kind: Kind
    message: str
    first_failing_layer: str | None = None
    bridge_restarts: int | None = None  # the watchdog's running count, when it was read
    checked_at: datetime


class WatchdogReport(BaseModel):
    bridge_state: str
    bridge_detail: str
    bridge_layer: str | None
    bridge_restarts: int
    plugin_state: str


WatchdogRead = WatchdogReport | Literal["refused", "offline", "unreadable"]


def refused(error: BaseException) -> bool:
    """A refused connection means the machine answered: it's up, the service isn't."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ConnectionRefusedError) or "refused" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


async def read_watchdog(config: WatchdogConfig, timeout: float) -> WatchdogRead:
    headers = {"Authorization": f"Bearer {os.environ.get(config.token_env, '')}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(config.url, headers=headers)
            response.raise_for_status()
            body = response.json()
    except httpx.ConnectError as error:
        return "refused" if refused(error) else "offline"
    except httpx.TimeoutException, httpx.NetworkError:
        return "offline"
    except httpx.HTTPError, ValueError:  # wrong token, server error, or not JSON
        return "unreadable"
    try:
        return WatchdogReport(
            bridge_state=body["bridge"]["state"],
            bridge_detail=body["bridge"]["detail"],
            bridge_layer=body["bridge"].get("first_failing_layer"),
            bridge_restarts=body["bridge"]["restarts"],
            plugin_state=body["plugin"]["state"],
        )
    except KeyError, TypeError, ValueError:
        return "unreadable"


async def diagnose(
    state: PluginState,
    health: Health | None,
    watchdog: WatchdogConfig | None,
    timeout: float = 5,
    seen_restarts: int | None = 0,
) -> ConnectionState:
    """`seen_restarts` is the watchdog's restart count at the last read, so a restart is
    reported once rather than for as long as the watchdog runs; None (never read) only
    records the count, so restarts from before the app started aren't news."""
    report: WatchdogReport | str | None = None

    def result(kind: Kind, message: str, layer: str | None = None) -> ConnectionState:
        restarts = report.bridge_restarts if isinstance(report, WatchdogReport) else None
        return ConnectionState(
            plugin_id=state.id,
            kind=kind,
            message=message,
            first_failing_layer=layer,
            bridge_restarts=restarts,
            checked_at=datetime.now(UTC),
        )

    if state.status == "connected" and health is not None:
        failing = next((check for check in health.checks if not check.ok), None)
        if failing is not None:
            if health.repair_actions:  # restartable: the watchdog or a repair is on it
                return result("bridge_restarting", f"Bridge is down → restarting. {failing.detail}".rstrip(), failing.layer)
            return result("owner_action", failing.detail, failing.layer)
        if watchdog is not None:
            report = await read_watchdog(watchdog, timeout)
            if isinstance(report, WatchdogReport) and seen_restarts is not None and report.bridge_restarts > seen_restarts:
                return result("bridge_restarted", "Bridge restarted. Mail is flowing again.")
        return result("ok", "Connected.")
    if state.status == "disabled":
        return result("plugin_failed", "Disabled in plugins.yaml.")
    if state.status == "refused":
        return result("owner_action", state.reason or "The plugin was refused.")
    if watchdog is None:
        return result("plugin_failed", state.reason or f"The {state.id} plugin isn't answering.")

    report = await read_watchdog(watchdog, timeout)
    if report == "offline":
        return result("machine_offline", f"{watchdog.machine} is offline.")
    if report == "refused":
        return result("waiting_for_login", f"Waiting for login on {watchdog.machine}.")
    if not isinstance(report, WatchdogReport):
        return result(
            "plugin_failed", f"The {state.id} plugin isn't answering and the watchdog on {watchdog.machine} can't be read; check its token."
        )
    if report.bridge_state == "needs_owner":
        return result("owner_action", report.bridge_detail, report.bridge_layer)
    if report.plugin_state == "needs_owner":
        return result("owner_action", f"The {state.id} plugin keeps stopping; check its logs on {watchdog.machine}.")
    if report.bridge_state == "restarting":
        return result("bridge_restarting", f"Bridge is down → restarting. {report.bridge_detail}".rstrip(), report.bridge_layer)
    return result("plugin_restarting", f"The {state.id} plugin is down → restarting.")
