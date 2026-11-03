# backend/app/models/job.py
"""One action the owner needs to take or approve, over one or more messages (spec §4)."""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

Verb = Literal["reply", "forward", "digest", "snooze", "follow_up", "todo", "archive_noise", "unsubscribe"]
JobState = Literal["open", "sending", "snoozed", "done", "dismissed", "failed", "handled_elsewhere"]
PermissionLevel = Literal["autonomous", "ask", "never_auto"]


class Artifacts(BaseModel):
    """What the job saves the owner (spec §8 step 5); a deadline is the job's `due`."""

    draft: str | None = None
    forward_to: str | None = None
    options: list[str] = Field(default_factory=list)
    link: str | None = None
    digest: str | None = None
    noise_rationale: str | None = None


class Job(Document):
    owner_id: str
    verb: Verb
    title: str
    evidence: list[str] = Field(default_factory=list)  # verbatim quotes from the messages
    artifacts: Artifacts
    due: datetime | None = None
    state: JobState = "open"
    message_ids: list[PydanticObjectId] = Field(min_length=1)
    permission_level: PermissionLevel | None = None  # the level it ran under, once acted on
    # An ask-owner card (§8.5, §10.2): no valid proposal, so the owner picks; never a guess.
    ask_owner: bool = False
    suggested_verbs: list[Verb] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)  # why validation sent it to the owner
    # First-connect mail (§5.3): every decision on it is `ask`, whatever the verb's permission (#71 enforces).
    requires_approval: bool = False
    error: str | None = None  # why finishing it didn't go through, naming the plugin (§10.3, AC-1.3)
    sending_since: datetime | None = None  # when execute() claimed it; a stale claim (a crash) can be retried
    sent_at: datetime | None = None  # its reply/forward went out: a retry only archives, never resends
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "jobs"
        indexes = [IndexModel([("owner_id", ASCENDING), ("message_ids", ASCENDING)])]
