# backend/app/plugins/diagnosis.py
"""One plain-language connection state per plugin, from its `health` and (for plugins on
another machine) that machine's watchdog status endpoint (spec §6.3)."""

import os
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel

from app.plugins.config import WatchdogConfig
from app.plugins.state import PluginState
from mailbox_contract import Health

Kind = Literal[
    "ok", "bridge_restarted", "bridge_restarting", "plugin_restarting", "plugin_failed",
    "owner_action", "machine_offline", "waiting_for_login",
]


class ConnectionState(BaseModel):
    plugin_id: str
    kind: Kind
    message: str
    first_failing_layer: str | None = None
    checked_at: datetime


class WatchdogReport(BaseModel):
    bridge_state: str
    bridge_detail: str
    bridge_restarts: int
    plugin_state: str


def refused(error: BaseException) -> bool:
    """A refused connection means the machine answered: it's up, the service isn't."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ConnectionRefusedError) or "refused" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


async def read_watchdog(config: WatchdogConfig, timeout: float) -> WatchdogReport | Literal["refused", "offline"]:
    headers = {"Authorization": f"Bearer {os.environ.get(config.token_env, '')}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(config.url, headers=headers)
            response.raise_for_status()
            body = response.json()
    except httpx.ConnectError as error:
        return "refused" if refused(error) else "offline"
    except (httpx.TimeoutException, httpx.NetworkError):
        return "offline"
    return WatchdogReport(
        bridge_state=body["bridge"]["state"], bridge_detail=body["bridge"]["detail"],
        bridge_restarts=body["bridge"]["restarts"], plugin_state=body["plugin"]["state"],
    )


async def diagnose(
    state: PluginState, health: Health | None, watchdog: WatchdogConfig | None, timeout: float = 5
) -> ConnectionState:
    def result(kind: Kind, message: str, layer: str | None = None) -> ConnectionState:
        return ConnectionState(plugin_id=state.id, kind=kind, message=message, first_failing_layer=layer, checked_at=datetime.now(UTC))

    if state.status == "connected" and health is not None:
        failing = next((check for check in health.checks if not check.ok), None)
        if failing is not None:
            if health.repair_actions:  # restartable: the watchdog or a repair is on it
                return result("bridge_restarting", f"Bridge is down → restarting. {failing.detail}", failing.layer)
            return result("owner_action", failing.detail, failing.layer)
        if watchdog is not None:
            report = await read_watchdog(watchdog, timeout)
            if isinstance(report, WatchdogReport) and report.bridge_restarts > 0:
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
    if report.bridge_state == "needs_owner":
        return result("owner_action", report.bridge_detail)
    if report.plugin_state == "needs_owner":
        return result("owner_action", f"The {state.id} plugin keeps stopping; check its logs on {watchdog.machine}.")
    if report.bridge_state == "restarting":
        return result("bridge_restarting", f"Bridge is down → restarting. {report.bridge_detail}")
    return result("plugin_restarting", f"The {state.id} plugin is down → restarting.")
