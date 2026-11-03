"""Validate stage (spec §8.5): deterministic checks after the AI. A proposal that is grounded,
specific and injection-safe becomes a job; anything else becomes an ask-owner job. Never a guess."""

import re
from collections.abc import Sequence

from app.models.job import Artifacts, Job, Verb
from app.models.message import Message
from app.pipeline.proposal import Proposal

# shortcut: a fixed floor; set it from the calibration metrics (#92) once there's a test set.
CONFIDENCE_FLOOR = 0.5

REQUIRED_ARTIFACTS: dict[Verb, tuple[tuple[str, ...], str]] = {
    "reply": (("draft", "options"), "a reply needs a draft or options"),
    "forward": (("draft",), "a forward needs a draft"),
    "digest": (("digest", "noise_rationale"), "a digest needs a summary or a reason"),
    "snooze": (("due",), "a snooze needs a date"),
    "follow_up": (("due",), "a follow-up needs a date"),
    "todo": (("link", "due"), "a todo needs a link or a deadline"),
    "archive_noise": (("noise_rationale",), "archiving as noise needs a reason"),
    "unsubscribe": (("noise_rationale",), "unsubscribing needs a reason"),
}
# A title that is only the verb says nothing, however it's punctuated ("Reply.", "Follow-up!").
VERB_TITLES = {re.sub(r"[^a-z]", "", verb) for verb in REQUIRED_ARTIFACTS}
URL = re.compile(r"https?://[^\s<>]+")
TRAILING_PUNCTUATION = ".,;:!?)]'\""


def problems(proposal: Proposal, body: str, forward_history: Sequence[str]) -> list[str]:
    """Why the proposal can't become a job; empty when it can. `body` is the minimized text the AI saw."""
    found = []
    if proposal.needs_owner:
        found.append("the AI wants the owner to decide")
    if proposal.confidence < CONFIDENCE_FLOOR:
        found.append("the AI isn't confident")
    if re.sub(r"[^a-z]", "", proposal.title.lower()) in VERB_TITLES | {""}:
        found.append("the title doesn't say what this email is")
    found += grounding_problems(proposal, body)
    fields, missing = REQUIRED_ARTIFACTS[proposal.verb]
    if not any(present(getattr(proposal, field)) for field in fields):
        found.append(missing)
    found += injection_problems(proposal, body, forward_history)
    return found


def grounding_problems(proposal: Proposal, body: str) -> list[str]:
    """Every quote must be in the email word for word; only line breaks and spacing may differ."""
    if not proposal.evidence:
        return ["no evidence from the email"]
    if not all(collapsed(quote) for quote in proposal.evidence):
        return ["blank evidence"]  # "" is in every text, so it would ground anything
    text = collapsed(body)
    return [f"evidence not in the email: {quote!r}" for quote in proposal.evidence if collapsed(quote) not in text]


def injection_problems(proposal: Proposal, body: str, forward_history: Sequence[str]) -> list[str]:
    """Links must come from the email (never invented); recipients only from the owner's history."""
    found = []
    links = {url.rstrip(TRAILING_PUNCTUATION) for url in URL.findall(body)}
    if proposal.link and proposal.link not in links:  # a whole link, not a prefix of a longer one
        found.append(f"link not in the email: {proposal.link}")
    history = {address.strip().lower() for address in forward_history}
    if proposal.forward_to and proposal.forward_to.strip().lower() not in history:
        found.append(f"forward recipient not from history: {proposal.forward_to}")
    return found


def present(value: object) -> bool:
    """A step-saving artifact has content: blank strings and blank options don't count."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(present(item) for item in value)
    return value is not None


def collapsed(text: str) -> str:
    return " ".join(text.split())


def to_job(message: Message, proposal: Proposal, body: str, forward_history: Sequence[str]) -> Job:
    assert message.id is not None, "jobs reference stored messages"
    found = problems(proposal, body, forward_history)
    if found:
        return Job(
            owner_id=message.owner_id, verb=proposal.verb, title=message.subject.strip() or "(no subject)",
            artifacts=Artifacts(), message_ids=[message.id],
            ask_owner=True, suggested_verbs=[proposal.verb], problems=found,
        )
    return Job(
        owner_id=message.owner_id, verb=proposal.verb, title=proposal.title, evidence=proposal.evidence,
        artifacts=Artifacts.model_validate(proposal.model_dump(include={"draft", "forward_to", "options", "link", "digest", "noise_rationale"})),
        due=proposal.due, message_ids=[message.id],
    )
