"""A stored, deterministic decision learned from the owner (spec §4 Rule): mail from this sender
or list gets this verb. Rules outrank the AI (§8.3)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.job import Verb

RuleMatch = Literal["sender", "list_id"]


class Rule(Document):
    owner_id: str
    match: RuleMatch
    value: str  # normalized with app.pipeline.rules.rule_key
    verb: Verb
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "rules"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("match", ASCENDING), ("value", ASCENDING)], unique=True),
        ]
