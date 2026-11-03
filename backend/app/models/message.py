# backend/app/models/message.py
"""One copy of a mail in one account (spec §4). The same mail in two accounts is two
messages with the same `message_id`, which one job can reference together (spec §5.3)."""

import re
from datetime import datetime
from typing import Literal

from beanie import Document
from pymongo import ASCENDING, DESCENDING, IndexModel

from mailbox_contract import Address


class Message(Document):
    owner_id: str
    plugin_id: str
    folder: Literal["inbox", "sent"] = "inbox"  # sent mail feeds voice, forward history and follow_up (§5.2)
    ref: str  # opaque and stable within the plugin
    message_id: str  # RFC 5322 Message-ID
    sender: Address
    to: list[Address]
    cc: list[Address]
    date: datetime
    subject: str
    snippet: str
    list_id: str | None = None
    in_reply_to: str | None = None
    first_pass: bool = False  # arrived in the first-connect pass: every decision on it is `ask` (spec §5.3)
    pipeline_done: bool = False  # the pipeline made its job (or ask-owner job) for this inbox message  # arrived in the first-connect pass: every decision on it is `ask` (spec §5.3)

    class Settings:
        name = "messages"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("plugin_id", ASCENDING), ("ref", ASCENDING)], unique=True),
            IndexModel([("owner_id", ASCENDING), ("message_id", ASCENDING)]),
            IndexModel([("owner_id", ASCENDING), ("folder", ASCENDING), ("date", DESCENDING)]),
        ]


async def recent_sent(owner_id: str, limit: int, to: str | None = None) -> list[Message]:
    """The owner's newest sent mail, optionally to one correspondent: their voice and history."""
    query = Message.find(Message.owner_id == owner_id, Message.folder == "sent")
    if to is not None:
        query = query.find({"to.email": {"$regex": f"^{re.escape(to)}$", "$options": "i"}})
    return await query.sort("-date").limit(limit).to_list()
