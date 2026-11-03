"""Rules stage (spec §8.3): if a stored rule matches, its verb wins and the AI only fills in details."""

import re

from app.models.message import Message
from app.models.rule import Rule, RuleMatch
from app.pipeline.proposal import Proposal

LIST_IDENTIFIER = re.compile(r"<([^<>]+)>")


def rule_key(match: RuleMatch, raw: str) -> str:
    """Senders compare case-insensitively; a List-Id compares by its <identifier> (RFC 2919)."""
    if match == "list_id" and (identifier := LIST_IDENTIFIER.search(raw)):
        raw = identifier.group(1)
    return raw.strip().lower()


async def matching_rule(owner_id: str, message: Message) -> Rule | None:
    """A List-Id rule first (the more specific stream), then a sender rule."""
    candidates: list[tuple[RuleMatch, str]] = [("sender", message.sender.email)]
    if message.list_id:
        candidates.insert(0, ("list_id", message.list_id))
    for match, raw in candidates:
        rule = await Rule.find_one(Rule.owner_id == owner_id, Rule.match == match, Rule.value == rule_key(match, raw))
        if rule is not None:
            return rule
    return None


def apply_rule(proposal: Proposal, rule: Rule | None) -> Proposal:
    """The rule's verb wins and the owner isn't asked; the AI's details (title, draft, …) stay."""
    if rule is None:
        return proposal
    return proposal.model_copy(update={"verb": rule.verb, "needs_owner": False})
