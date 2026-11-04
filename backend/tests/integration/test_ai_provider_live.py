# Live Anthropic API: costs a few cents per run, skipped when no key is set.
import os
from typing import Literal

import pytest
from pydantic import BaseModel

from app.config import get_settings
from app.services.ai_provider import provider_for

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
    ),
]


class Proposal(BaseModel):
    verb: Literal["reply", "archive", "schedule"]
    title: str


async def test_anthropic_provider_returns_schema_valid_result():
    prompt = (
        "Email from ana@example.com, subject 'Q3 budget': "
        "'Can we meet Thursday at 3pm to go over the Q3 budget?' "
        "Propose the single best action."
    )

    proposal = await provider_for(get_settings().ai_provider, get_settings().ai_model).propose(prompt, Proposal)

    assert isinstance(proposal, Proposal)
    assert proposal.verb == "schedule"
    assert proposal.title.strip()
