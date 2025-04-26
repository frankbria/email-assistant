# backend/tests/test_services/test_context_classifier.py
import os
import importlib
import pytest


@pytest.mark.asyncio
async def test_classify_context_uses_ai(monkeypatch):
    # Enable AI mode via environment and reload module
    monkeypatch.setenv("USE_AI_CONTEXT", "true")
    import app.services.context_classifier as context_classifier

    importlib.reload(context_classifier)

    # Stub AI-based classifier to return a known label
    async def fake_ai(subject, body):
        return "ai_context"

    monkeypatch.setattr(context_classifier, "classify_context_ai", fake_ai)

    # Call the unified classifier and expect AI result
    result = await context_classifier.classify_context("Subject", "Body text")
    assert result == "ai_context"
