"""One action taken on the owner's mail, by the app or the owner: the History timeline (spec §9, §10.6)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.job import PermissionLevel

Action = Literal["sent", "archived", "done", "snoozed", "dismissed", "restored"]
Actor = Literal["app", "owner"]


class ActionLogEntry(Document):
    owner_id: str
    action: Action
    job_id: PydanticObjectId
    message_ids: list[PydanticObjectId]  # what an archive moved out of the inbox, else the job's messages
    by: Actor
    permission_level: PermissionLevel | None  # None: no permission governs it (a dismissal, an undo)
    ok: bool
    error: str | None = None
    undoable: bool = False  # it moved mail out of the inbox, so a restore puts it back; a send never is
    undone: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "action_log"
        indexes = [IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)])]
