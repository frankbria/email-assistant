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
    draft: str | None = None
    options: list[str] = Field(default_factory=list)
    due: datetime | None = None
    confidence: float = Field(ge=0, le=1)
