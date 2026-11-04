"""The History timeline (spec §9, §10.6): every action the app or the owner took, newest first, and undo where
possible (restore after an archive; a sent email can't be unsent)."""

import logging

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.routers.jobs import plugin_registry
from app.auth import OwnerId
from app.executor import NotUndoable, undo
from app.models.action_log import ActionLogEntry
from app.models.message import Message
from app.pipeline.rules import ask_first_from_now_on
from app.plugins.registry import PluginRegistry
from mailbox_contract import Address

logger = logging.getLogger(__name__)
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
    """Returns the restore's own entry: ok, or failed with why (the original then stays undoable). Restoring what the
    app archived on its own corrects it (§10.4, AC-2.4); undoing the owner's own archive only changes their mind."""
    entry = await ActionLogEntry.find_one(ActionLogEntry.id == entry_id, ActionLogEntry.owner_id == owner_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    try:
        restored = await undo(entry, plugins)
    except NotUndoable as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    # Not every app archive is its own call: a late copy follows the owner's approval and keeps its `ask` level.
    if restored.ok and entry.by == "app" and entry.permission_level == "autonomous":
        try:  # the mail is already back: a failed lesson mustn't turn that into an error
            message = await Message.get(entry.message_ids[0])
            assert message is not None, "an archive's messages are stored before it"
            await ask_first_from_now_on(message)
        except Exception:
            logger.exception("Couldn't learn from the restore of history entry %s", entry_id)
    return restored
