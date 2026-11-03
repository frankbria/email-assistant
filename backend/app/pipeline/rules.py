"""Rules stage (spec §8.3): if a stored rule matches, its verb wins and the AI only fills in details."""

from app.models.message import Message
from app.models.rule import Rule, RuleMatch, rule_key
from app.pipeline.proposal import ARTIFACTS, Proposal


async def matching_rule(owner_id: str, message: Message) -> Rule | None:
    """A List-Id rule first (the more specific stream), then a sender rule."""
    candidates: list[tuple[RuleMatch, str]] = [("list_id", message.list_id or ""), ("sender", message.sender.email)]
    for match, raw in candidates:
        key = rule_key(match, raw)
        if not key:
            continue  # a missing sender or list identifies nothing
        rule = await Rule.find_one(Rule.owner_id == owner_id, Rule.match == match, Rule.value == key)
        if rule is not None:
            return rule
    return None


def apply_rule(proposal: Proposal, rule: Rule | None) -> Proposal:
    """The rule's verb wins and the owner isn't asked which action (permissions, §9, still decide
    whether acting asks first). Details the AI wrote for another verb are dropped: validation (§8.5)
    then routes a proposal with nothing left for the rule's verb to the owner rather than guessing."""
    if rule is None:
        return proposal
    if rule.verb == proposal.verb:
        return proposal.model_copy(update={"needs_owner": False})
    cleared = {field: Proposal.model_fields[field].get_default(call_default_factory=True) for field in ARTIFACTS}
    return proposal.model_copy(update={"verb": rule.verb, "needs_owner": False, **cleared})
