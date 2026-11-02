import importlib.util

import pytest

from app.config import Settings
from app.services import ai_provider
from app.services.ai_provider import AnthropicProvider, get_ai_provider


def test_default_provider_is_anthropic_with_current_claude_model(monkeypatch):
    monkeypatch.setattr(ai_provider, "get_settings", lambda: Settings())

    provider = get_ai_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-opus-5-5"


def test_model_comes_from_config(monkeypatch):
    monkeypatch.setattr(
        ai_provider, "get_settings", lambda: Settings(ai_model="claude-sonnet-5-5")
    )

    provider = get_ai_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet-5-5"


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(
        ai_provider, "get_settings", lambda: Settings(ai_provider="nope")
    )

    with pytest.raises(ValueError, match="nope"):
        get_ai_provider()


def test_openai_is_not_installed():
    assert importlib.util.find_spec("openai") is None
