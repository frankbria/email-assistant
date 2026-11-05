# Live Anthropic API (#63 AC): costs cents per run; opt in with `uv run pytest -m integration`.
import os
import re
from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId

from app.models.message import Message
from app.pipeline.proposal import Proposal
from app.pipeline.examples import record_example, similar_examples
from app.pipeline.propose import propose
from app.config import get_settings
from app.services.ai_provider import provider_for
from tests.fixtures.proposal_corpus import CORPUS, EARLIER_RIDE, NEXT_RIDE, ProposalCase

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

BARE_TITLES = {
    "reply",
    "forward",
    "digest",
    "snooze",
    "follow up",
    "follow_up",
    "todo",
    "archive",
    "archive noise",
    "archive_noise",
    "unsubscribe",
    "reply to email",
    "archive email",
    "forward email",
}
STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "for",
    "and",
    "on",
    "in",
    "at",
    "your",
    "from",
    "this",
    "with",
    "about",
    "email",
    "message",
    "mail",
    "reply",
    "forward",
    "archive",
    "noise",
    "digest",
    "snooze",
    "todo",
    "follow",
    "unsubscribe",
    "re",
    "fwd",
    "com",
    "example",
    "regarding",
    "update",
    "new",
}


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOPWORDS and len(word) > 2}


def inbox_message(case: ProposalCase) -> Message:
    return Message.model_validate(
        {
            "_id": PydanticObjectId(),
            "owner_id": "owner-1",
            "plugin_id": "proton",
            "ref": case.name,
            "message_id": f"<{case.name}@x>",
            "sender": {"email": case.sender},
            "to": [{"email": "frank@example.com"}],
            "cc": [],
            "date": datetime(2026, 11, 2, tzinfo=UTC),
            "subject": case.subject,
            "snippet": case.body[:200],
            "list_id": case.list_id,
        }
    )


@pytest.mark.parametrize("case", CORPUS, ids=[case.name for case in CORPUS])
async def test_each_proposal_is_schema_valid_with_a_message_specific_title(test_db, case: ProposalCase):
    message = inbox_message(case)

    proposal = await propose(message, case.body, provider_for(get_settings().ai_provider, get_settings().ai_model))

    assert isinstance(proposal, Proposal)  # parsed against the schema by the provider
    assert proposal.title.strip().lower() not in BARE_TITLES
    # Specific = names something from this mail's subject or body, not just the verb, the sender or generic words.
    assert words(proposal.title) & words(f"{case.subject} {case.body}"), proposal.title


async def test_the_proposal_follows_the_owners_example_for_a_near_identical_message(test_db):
    """#82 AC: the owner replied to the last ride notice, so the next one gets a reply too."""
    await record_example(inbox_message(EARLIER_RIDE), EARLIER_RIDE.body, "reply", "ask_owner")
    message = inbox_message(NEXT_RIDE)
    examples = [example.summary() for example in await similar_examples(message, NEXT_RIDE.body)]

    proposal = await propose(message, NEXT_RIDE.body, provider_for(get_settings().ai_provider, get_settings().ai_model), examples=examples)

    assert len(examples) == 1
    assert proposal.verb == "reply", proposal
