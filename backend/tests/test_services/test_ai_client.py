import logging
import pytest
import openai
from types import SimpleNamespace

from app.services.ai_client import classify_context_ai, _VALID_CATEGORIES

pytestmark = pytest.mark.asyncio


async def fake_acreate_success(*args, **kwargs):
    # Return a valid category (first from _VALID_CATEGORIES)
    valid_category = sorted(_VALID_CATEGORIES)[0]
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=valid_category))]
    )


async def fake_acreate_invalid(*args, **kwargs):
    # Return an unexpected category
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="invalid_category"))]
    )


async def fake_acreate_error(*args, **kwargs):
    # Simulate API failure
    raise Exception("API down")


async def test_classify_context_ai_valid(monkeypatch):
    """
    When OpenAI returns a valid category, classify_context_ai should return it as-is.
    """
    monkeypatch.setattr(openai.ChatCompletion, "acreate", fake_acreate_success)
    category = await classify_context_ai("Test", "Body")
    assert category in _VALID_CATEGORIES


async def test_classify_context_ai_invalid_category(monkeypatch, caplog):
    """
    When OpenAI returns an unexpected label, classify_context_ai should warn and return 'other'.
    """
    # Ensure API key is set so classify_context_ai does not early-return
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai.ChatCompletion, "acreate", fake_acreate_invalid)
    caplog.set_level(logging.WARNING, logger="app.services.ai_client")

    category = await classify_context_ai("Test", "Body")
    assert category == "other"


async def test_classify_context_ai_error(monkeypatch, caplog):
    """
    If the OpenAI client raises an exception, classify_context_ai should log an error and return 'other'.
    """
    # Ensure API key is set so classify_context_ai does not early-return
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai.ChatCompletion, "acreate", fake_acreate_error)
    caplog.set_level(logging.ERROR, logger="app.services.ai_client")

    category = await classify_context_ai("Test", "Body")
    assert category == "other"
