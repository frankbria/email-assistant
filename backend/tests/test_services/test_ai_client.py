import pytest

from app.services import ai_client
from app.services.ai_client import ContextClassification, classify_context_ai
from tests.utils.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ai_context_enabled(monkeypatch):
    monkeypatch.setenv("USE_AI_CONTEXT", "true")


async def test_classify_context_ai_returns_provider_category(monkeypatch, ai_context_enabled):
    provider = FakeAIProvider(ContextClassification(category="scheduling"))
    monkeypatch.setattr(ai_client, "get_ai_provider", lambda: provider)

    category = await classify_context_ai("Meeting", "Can we meet Thursday?")

    assert category == "scheduling"
    assert "Can we meet Thursday?" in provider.prompts[0]


async def test_classify_context_ai_falls_back_to_other_on_error(monkeypatch, ai_context_enabled):
    monkeypatch.setattr(
        ai_client, "get_ai_provider", lambda: FakeAIProvider(error=Exception("API down"))
    )

    assert await classify_context_ai("Test", "Body") == "other"


async def test_classify_context_ai_disabled_skips_provider(monkeypatch):
    monkeypatch.setenv("USE_AI_CONTEXT", "false")
    provider = FakeAIProvider(ContextClassification(category="sales"))
    monkeypatch.setattr(ai_client, "get_ai_provider", lambda: provider)

    assert await classify_context_ai("Test", "Body") == "other"
    assert provider.prompts == []
