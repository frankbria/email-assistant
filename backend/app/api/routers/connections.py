# backend/app/api/routers/connections.py
"""The Connections screen's data: one row per configured mailbox plugin (spec §10.8)."""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.auth import OwnerId
from app.plugins.diagnosis import ConnectionState
from app.plugins.registry import PluginRegistry
from app.plugins.state import PluginStatus

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])

REPAIRING_KINDS = {"bridge_restarting", "plugin_restarting"}


class Connection(BaseModel):
    plugin_id: str
    status: PluginStatus
    account: str | None
    reason: str | None
    diagnosis: ConnectionState | None
    repairing: bool
    # shortcut: always None until the sync engine (#55) records successful syncs; fill it then.
    last_synced_at: datetime | None = None


@router.get("", response_model=list[Connection])
async def list_connections(_owner_id: OwnerId, request: Request) -> list[Connection]:
    plugins: PluginRegistry = request.app.state.plugins
    rows = []
    for plugin_id, state in plugins.states.items():
        diagnosis = plugins.diagnoses.get(plugin_id)
        rows.append(
            Connection(
                plugin_id=plugin_id,
                status=state.status,
                account=state.info.account if state.info else None,
                reason=state.reason,
                diagnosis=diagnosis,
                repairing=diagnosis is not None and diagnosis.kind in REPAIRING_KINDS,
            )
        )
    return rows
