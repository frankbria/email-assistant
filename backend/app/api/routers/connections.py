# backend/app/api/routers/connections.py
"""The Connections screen's data: one row per configured mailbox plugin (spec §10.8)."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth import OwnerId
from app.models.sync_cursor import SyncCursor
from app.plugins.diagnosis import ConnectionState, read_watchdog
from app.plugins.registry import PluginRegistry
from app.plugins.setup import Checklist, build_checklist, is_gmail
from app.plugins.state import PluginStatus

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])

REPAIRING_KINDS = {"bridge_restarting", "plugin_restarting"}


class Connection(BaseModel):
    plugin_id: str
    status: PluginStatus
    plugin_name: str | None
    account: str | None
    reason: str | None
    diagnosis: ConnectionState | None
    repairing: bool
    last_synced_at: datetime | None


@router.get("", response_model=list[Connection])
async def list_connections(owner_id: OwnerId, request: Request) -> list[Connection]:
    plugins: PluginRegistry = request.app.state.plugins
    inbox_cursors = SyncCursor.find(SyncCursor.owner_id == owner_id, SyncCursor.folder == "inbox")
    last_synced = {cursor.plugin_id: cursor.updated_at async for cursor in inbox_cursors}
    rows = []
    for plugin_id, state in plugins.states.items():
        diagnosis = plugins.diagnoses.get(plugin_id)
        rows.append(
            Connection(
                plugin_id=plugin_id,
                status=state.status,
                plugin_name=state.info.plugin_name if state.info else None,
                account=state.info.account if state.info else None,
                reason=state.reason,
                diagnosis=diagnosis,
                repairing=diagnosis is not None and diagnosis.kind in REPAIRING_KINDS,
                last_synced_at=last_synced.get(plugin_id),
            )
        )
    return rows


@router.post("/{plugin_id}/check", response_model=Checklist)
async def check_connection(plugin_id: str, _owner_id: OwnerId, request: Request) -> Checklist:
    """Check one plugin now (the guided setup's live checks) and return its checklist."""
    plugins: PluginRegistry = request.app.state.plugins
    if plugin_id not in plugins.configs:
        raise HTTPException(status_code=404, detail=f"No plugin '{plugin_id}' in plugins.yaml")
    await plugins.check(plugin_id)
    # Read this check's state and health before awaiting again: the refresh loop may re-check meanwhile.
    config, state, health = plugins.configs[plugin_id], plugins.states[plugin_id], plugins.healths[plugin_id]
    watchdog = await read_watchdog(config.watchdog, timeout=5) if config.watchdog else None
    # Only once the connection works: the check needs it, and it writes a probe message.
    healthy = health is not None and all(check.ok for check in health.checks)
    warnings = await plugins.setup_warnings(plugin_id) if is_gmail(state) and healthy else []
    return build_checklist(config, state, health, watchdog, warnings)
