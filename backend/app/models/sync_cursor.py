# backend/app/models/sync_cursor.py
"""Where sync left off in one plugin folder; `list_messages` cursors survive restarts (spec §5.2)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class SyncCursor(Document):
    owner_id: str
    plugin_id: str
    folder: Literal["inbox", "sent"]
    cursor: str | None = None
    first_pass_complete: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "sync_cursors"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("plugin_id", ASCENDING), ("folder", ASCENDING)], unique=True),
        ]
