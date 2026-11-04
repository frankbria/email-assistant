"""The History timeline (spec §9, §10.6): every action the app or the owner took, newest first, and undo where
possible (restore after an archive; a sent email can't be unsent)."""

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.routers.jobs import plugin_registry
from app.auth import OwnerId
from app.executor import NotUndoable, undo
from app.models.action_log import ActionLogEntry
from app.models.message import Message
from app.plugins.registry import PluginRegistry
from mailbox_contract import Address

router = APIRouter(prefix="/api/v1/history", tags=["history"])


class HistoryCard(BaseModel):
    entry: ActionLogEntry
    sender: Address
    subject: str


@router.get("", response_model=list[HistoryCard])
async def list_history(owner_id: OwnerId) -> list[HistoryCard]:
    # shortcut: returns the whole history; page it (e.g. a `before` timestamp) once it gets long enough to be slow.
    entries = await ActionLogEntry.find(ActionLogEntry.owner_id == owner_id).sort("-created_at", "-_id").to_list()
    messages = await Message.find(In(Message.id, [entry.message_ids[0] for entry in entries if entry.message_ids])).to_list()
    by_id = {message.id: message for message in messages}
    return [
        HistoryCard(entry=entry, sender=by_id[entry.message_ids[0]].sender, subject=by_id[entry.message_ids[0]].subject)
        for entry in entries
        if entry.message_ids and entry.message_ids[0] in by_id
    ]


@router.post("/{entry_id}/undo", response_model=ActionLogEntry)
async def undo_entry(entry_id: PydanticObjectId, owner_id: OwnerId, plugins: PluginRegistry = Depends(plugin_registry)) -> ActionLogEntry:
    """Returns the restore's own entry: ok, or failed with why (the original then stays undoable)."""
    entry = await ActionLogEntry.find_one(ActionLogEntry.id == entry_id, ActionLogEntry.owner_id == owner_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    try:
        return await undo(entry, plugins)
    except NotUndoable as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
