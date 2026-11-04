"""Rules stage (spec §8.3): if a stored rule matches, its verb wins and the AI only fills in details.
Corrections (§10.4) teach and forget rules here."""

from datetime import UTC, datetime

from app.models.job import Verb
from app.models.message import Message
from app.models.rule import Rule, RuleMatch, rule_key
from app.pipeline.proposal import ARTIFACTS, Proposal


def stream_keys(message: Message) -> list[tuple[RuleMatch, str]]:
    """The message's List-Id first (the more specific stream), then its sender; a missing one identifies nothing."""
    candidates: list[tuple[RuleMatch, str]] = [("list_id", message.list_id or ""), ("sender", message.sender.email)]
    return [(match, key) for match, raw in candidates if (key := rule_key(match, raw))]


async def matching_rule(owner_id: str, message: Message) -> Rule | None:
    for match, key in stream_keys(message):
        rule = await Rule.find_one(Rule.owner_id == owner_id, Rule.match == match, Rule.value == key)
        if rule is not None:
            return rule
    return None


async def learn_rule(message: Message, verb: Verb) -> None:
    """The owner's verb for the message's stream from now on. The rule that decided this message is the one
    corrected; with none, the stream matching_rule checks first gets a new one, so it decides next time."""
    decided = await matching_rule(message.owner_id, message)
    keys = [(decided.match, decided.value)] if decided else stream_keys(message)
    if not keys:
        return
    match, key = keys[0]
    await Rule.get_pymongo_collection().update_one(
        {"owner_id": message.owner_id, "match": match, "value": key},
        {"$set": {"verb": verb}, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
    )


async def forget_noise_rules(message: Message) -> None:
    """Any rule that would archive the message's stream as noise; rules for other verbs stay."""
    for match, key in stream_keys(message):
        await Rule.find(Rule.owner_id == message.owner_id, Rule.match == match, Rule.value == key, Rule.verb == "archive_noise").delete()


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
