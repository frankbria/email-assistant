"""The AI's structured proposal for one message (spec §8.4). Rules (§8.3) may fix its verb;
validation (§8.5) decides whether it becomes a job or an ask-owner card."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.job import Verb


class Proposal(BaseModel):
    needs_owner: bool
    verb: Verb
    title: str  # specific to the message, never a bare verb
    evidence: list[str] = Field(default_factory=list)  # verbatim quotes from the minimized message
    draft: str | None = None  # reply / forward text in the owner's voice
    options: list[str] = Field(default_factory=list)  # 2-3 drafted replies: yes / no / later
    due: datetime | None = None  # snooze until, follow-up by, or the todo's deadline
    forward_to: str | None = None  # chosen only from the owner's forwarding history
    link: str | None = None  # the todo's link, copied exactly from the mail
    noise_rationale: str | None = None  # why archive_noise / digest / unsubscribe needs no owner
    confidence: float = Field(ge=0, le=1)
