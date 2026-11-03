"""AI calls made per calendar month, for the optional spend cap (spec §5.3)."""

from datetime import datetime

from beanie import Document
from pymongo import ASCENDING, IndexModel


class AiUsage(Document):
    month: str  # "2026-11" (UTC)
    calls: int = 0
    cap_warned_at: datetime | None = None  # the month's one warning that the cap was reached

    class Settings:
        name = "ai_usage"
        indexes = [IndexModel([("month", ASCENDING)], unique=True)]
