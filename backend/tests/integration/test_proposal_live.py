# Live Anthropic API (#63 AC): costs cents per run; opt in with `uv run pytest -m integration`.
import os
import re
from datetime import UTC, datetime

import pytest

from app.models.message import Message
from app.pipeline.proposal import Proposal
from app.pipeline.propose import propose
from app.services.ai_provider import get_ai_provider
from tests.fixtures.proposal_corpus import CORPUS, ProposalCase

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

BARE_TITLES = {"reply", "forward", "digest", "snooze", "follow up", "follow_up", "todo", "archive", "archive noise",
               "archive_noise", "unsubscribe", "reply to email", "archive email", "forward email"}
STOPWORDS = {"the", "a", "an", "to", "of", "for", "and", "on", "in", "at", "your", "from", "this", "with", "about"}


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOPWORDS and len(word) > 2}


@pytest.mark.parametrize("case", CORPUS, ids=[case.name for case in CORPUS])
async def test_each_proposal_is_schema_valid_with_a_message_specific_title(test_db, case: ProposalCase):
    message = Message.model_validate({
        "owner_id": "owner-1", "plugin_id": "proton", "ref": case.name, "message_id": f"<{case.name}@x>",
        "sender": {"email": case.sender}, "to": [{"email": "frank@example.com"}], "cc": [],
        "date": datetime(2026, 11, 2, tzinfo=UTC), "subject": case.subject, "snippet": case.body[:200],
        "list_id": case.list_id,
    })

    proposal = await propose(message, case.body, get_ai_provider())

    assert isinstance(proposal, Proposal)  # parsed against the schema by the provider
    assert proposal.title.strip().lower() not in BARE_TITLES
    assert words(proposal.title) & words(f"{case.sender} {case.subject} {case.body}"), proposal.title
