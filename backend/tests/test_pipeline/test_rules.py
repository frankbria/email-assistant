# Rules stage (spec §4 Rule, §8.3): a stored deterministic decision outranks the AI's verb.
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.models.message import Message
from app.models.rule import Rule
from app.pipeline.proposal import ARTIFACTS, Proposal
from app.pipeline.rules import apply_rule, matching_rule
from tests.utils.fakes import FakeAIProvider

OWNER = "owner-1"


def message_from(sender: str, list_id: str | None = None, owner_id: str = OWNER) -> Message:
    return Message.model_validate({
        "owner_id": owner_id, "plugin_id": "proton", "ref": "r1", "message_id": "<m@x>",
        "sender": {"email": sender}, "to": [], "cc": [], "date": datetime(2026, 11, 2, tzinfo=UTC),
        "subject": "Weekly deals", "snippet": "", "list_id": list_id,
    })


def ai_reply() -> Proposal:
    return Proposal(
        needs_owner=False, verb="reply", title="Reply to Shop about weekly deals",
        evidence=["Weekly deals"], draft="Thanks!", confidence=0.7,
    )


async def test_a_stored_sender_rule_wins_over_the_ai_verb(test_db):
    """AC: a rule for sender S -> archive_noise beats the AI's proposal for mail from S."""
    await Rule(owner_id=OWNER, match="sender", value="deals@shop.example", verb="archive_noise").insert()
    message = message_from("Deals@Shop.example")
    provider = FakeAIProvider(result=ai_reply())

    rule = await matching_rule(OWNER, message)
    decided = apply_rule(await provider.propose("prompt", Proposal), rule)

    assert decided.verb == "archive_noise" and not decided.needs_owner
    assert decided.title == "Reply to Shop about weekly deals"  # details stay the AI's


async def test_a_list_rule_is_more_specific_than_a_sender_rule(test_db):
    await Rule(owner_id=OWNER, match="sender", value="news@shop.example", verb="digest").insert()
    await Rule(owner_id=OWNER, match="list_id", value="deals.shop.example", verb="unsubscribe").insert()

    rule = await matching_rule(OWNER, message_from("news@shop.example", list_id="Shop Deals <Deals.Shop.Example>"))

    assert rule is not None and rule.verb == "unsubscribe"


async def test_without_a_matching_rule_the_ai_proposal_stands(test_db):
    await Rule(owner_id="someone-else", match="sender", value="a@example.com", verb="archive_noise").insert()

    rule = await matching_rule(OWNER, message_from("a@example.com", list_id="<other.list>"))

    assert rule is None
    assert apply_rule(ai_reply(), rule) == ai_reply()


async def test_the_owner_is_not_asked_when_a_rule_decides(test_db):
    unsure = ai_reply().model_copy(update={"needs_owner": True, "confidence": 0.2})
    rule = Rule(owner_id=OWNER, match="sender", value="a@example.com", verb="todo")

    assert apply_rule(unsure, rule).needs_owner is False


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_a_proposal_confidence_outside_zero_to_one_is_rejected(confidence: float):
    with pytest.raises(ValidationError, match="confidence"):
        Proposal.model_validate({**ai_reply().model_dump(), "confidence": confidence})


async def test_one_rule_per_owner_match_and_value(test_db):
    await Rule(owner_id=OWNER, match="sender", value="a@example.com", verb="todo").insert()

    with pytest.raises(DuplicateKeyError):
        await Rule(owner_id=OWNER, match="sender", value="a@example.com", verb="digest").insert()


async def test_rule_values_are_normalized_when_created(test_db):
    """Whoever creates a rule (corrections in M3), it matches, and case variants are one rule."""
    await Rule(owner_id=OWNER, match="list_id", value="Shop Deals <Deals.Shop.Example>", verb="unsubscribe").insert()

    rule = await matching_rule(OWNER, message_from("x@y.example", list_id="<deals.shop.example>"))

    assert rule is not None and rule.value == "deals.shop.example"
    with pytest.raises(DuplicateKeyError):
        await Rule(owner_id=OWNER, match="list_id", value="<DEALS.shop.example>", verb="digest").insert()


async def test_a_blank_sender_or_list_matches_no_rule(test_db):
    await Rule.get_pymongo_collection().insert_one({"owner_id": OWNER, "match": "sender", "value": "", "verb": "archive_noise"})
    await Rule.get_pymongo_collection().insert_one({"owner_id": OWNER, "match": "list_id", "value": "", "verb": "archive_noise"})

    assert await matching_rule(OWNER, message_from("", list_id="   ")) is None


async def test_details_written_for_another_verb_are_dropped_when_the_rule_changes_it(test_db):
    rule = Rule(owner_id=OWNER, match="sender", value="a@example.com", verb="archive_noise")

    written_for_reply = {"options": ["Yes", "No"], "forward_to": "a@x.example", "link": "https://x.example",
                         "noise_rationale": "n", "digest": "d", "due": datetime(2026, 12, 1, tzinfo=UTC)}
    decided = apply_rule(ai_reply().model_copy(update=written_for_reply), rule)

    assert {field: getattr(decided, field) for field in ARTIFACTS} == {field: Proposal.model_fields[field].get_default(call_default_factory=True) for field in ARTIFACTS}
    assert decided.title == ai_reply().title and decided.evidence == ai_reply().evidence


async def test_details_stay_when_the_rule_agrees_with_the_ai(test_db):
    rule = Rule(owner_id=OWNER, match="sender", value="a@example.com", verb="reply")

    assert apply_rule(ai_reply(), rule) == ai_reply()
