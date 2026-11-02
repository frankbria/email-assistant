# backend/app/models/message.py
"""One copy of a mail in one account (spec §4). The same mail in two accounts is two
messages with the same `message_id`, which one job can reference together (spec §5.3)."""

from datetime import datetime

from beanie import Document
from pymongo import ASCENDING, IndexModel

from mailbox_contract import Address


class Message(Document):
    owner_id: str
    plugin_id: str
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

    class Settings:
        name = "messages"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("plugin_id", ASCENDING), ("ref", ASCENDING)], unique=True),
            IndexModel([("owner_id", ASCENDING), ("message_id", ASCENDING)]),
        ]
