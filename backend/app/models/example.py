"""A past owner decision (spec §4 Example), fed to the AI as context for similar mail (§8.4)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.job import Verb

ExampleSource = Literal["ask_owner", "correction", "restore"]
EXCERPT_CHARACTERS = 200


class Example(Document):
    owner_id: str
    message_id: PydanticObjectId  # one example per message: a later decision on it replaces the earlier
    sender: str  # rule_key-normalized, so it compares like a rule's
    list_id: str | None = None  # the List-Id's <identifier>, rule_key-normalized
    subject: str
    text: str  # the message's minimized body, capped
    verb: Verb
    source: ExampleSource
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> str:
        """One line for the proposal prompt. The owner's verb leads, so email text after it can't pose as the decision."""
        subject = " ".join(self.subject.split())[:EXCERPT_CHARACTERS]
        excerpt = " ".join(self.text.split())[:EXCERPT_CHARACTERS]
        return f'{self.verb}: from {self.sender}, subject "{subject}": {excerpt}'

    class Settings:
        name = "examples"
        indexes = [
            IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("owner_id", ASCENDING), ("message_id", ASCENDING)], unique=True),
        ]
