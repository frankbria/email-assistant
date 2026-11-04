import importlib.util

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.services.ai_provider import AnthropicProvider, get_ai_provider, provider_for


def test_provider_is_reused_for_the_same_model():
    assert provider_for("anthropic", "claude-opus-5-5") is provider_for("anthropic", "claude-opus-5-5")


async def test_default_provider_is_anthropic_with_current_claude_model(test_db):
    provider = await get_ai_provider("owner-without-settings")

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-opus-5-5"


async def test_model_comes_from_config_until_the_owner_chooses(test_db, monkeypatch):
    monkeypatch.setenv("AI_MODEL", "claude-sonnet-5-5")
    get_settings.cache_clear()
    try:
        provider = await get_ai_provider("owner-without-settings")
    finally:
        get_settings.cache_clear()

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet-5-5"


def test_unknown_provider_is_rejected_at_startup():
    with pytest.raises(ValidationError, match="ai_provider"):
        Settings(ai_provider="nope")


def test_openai_is_not_installed():
    assert importlib.util.find_spec("openai") is None
