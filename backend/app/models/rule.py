"""A stored, deterministic decision learned from the owner (spec §4 Rule): mail from this sender
or list gets this verb. Rules outrank the AI (§8.3)."""

import re
from datetime import UTC, datetime
from typing import Literal, Self

from beanie import Document
from pydantic import Field, model_validator
from pymongo import ASCENDING, IndexModel

from app.models.job import Verb

RuleMatch = Literal["sender", "list_id"]
LIST_IDENTIFIER = re.compile(r"<([^<>]+)>")


def rule_key(match: RuleMatch, raw: str) -> str:
    """Senders compare case-insensitively; a List-Id compares by its <identifier> (RFC 2919)."""
    if match == "list_id" and (identifier := LIST_IDENTIFIER.search(raw)):
        raw = identifier.group(1)
    return raw.strip().lower()


class Rule(Document):
    owner_id: str
    match: RuleMatch
    value: str  # normalized on creation, so every creator's rules match and case variants collide
    verb: Verb
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def normalized(self) -> Self:
        self.value = rule_key(self.match, self.value)
        return self

    class Settings:
        name = "rules"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("match", ASCENDING), ("value", ASCENDING)], unique=True),
        ]
