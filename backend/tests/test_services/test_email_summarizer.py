# backend/tests/test_services/test_email_summarizer.py
import os
import importlib
import pytest
from types import SimpleNamespace
from app.models.email_message import EmailMessageBase
import app.services.email_summarizer as es_module


@pytest.mark.asyncio
async def test_generate_summary_from_subject():
    """
    Validates that when the subject clearly describes the email's purpose,
    it is used as the summary.
    This test ensures we don't overcomplicate when the subject is sufficient.
    """
    email = EmailMessageBase(
        subject="Meeting Request: Project Kickoff",
        body="Hi, I'd like to schedule a meeting to discuss the project kickoff. Please let me know your availability.",
        sender="test@example.com",
    )
    # Rule-based summarization (default USE_AI_SUMMARY=false)
    importlib.reload(es_module)
    summary = await es_module.generate_summary(email)
    assert (
        summary == "Handle: Meeting Request: Project Kickoff"
    ), "Clear subject should be used as summary"


@pytest.mark.asyncio
async def test_generate_summary_from_body():
    """
    Validates that when the subject is generic, the first meaningful sentence
    from the body is used as the summary.
    This test ensures we extract relevant information when the subject isn't descriptive.
    """
    email = EmailMessageBase(
        subject="Follow up",
        body="I'm writing to request a demo of your product next week. We're particularly interested in the enterprise features.",
        sender="prospect@example.com",
    )
    importlib.reload(es_module)
    summary = await es_module.generate_summary(email)
    assert (
        summary == "Follow up: I'm writing to request a demo of your product next week."
    ), "First meaningful sentence should be used as summary"


@pytest.mark.asyncio
async def test_generate_summary_empty_content():
    """
    Validates that the summarizer handles empty or invalid content gracefully.
    This test ensures the service doesn't break with edge cases.
    """
    email = EmailMessageBase(subject="", body="", sender="test@example.com")
    importlib.reload(es_module)
    summary = await es_module.generate_summary(email)
    assert summary == "No content available"


@pytest.mark.asyncio
async def test_generate_summary_ai(monkeypatch):
    # Enable AI summarization
    monkeypatch.setenv("USE_AI_SUMMARY", "true")

    # Reload modules if needed (optional after big env change)
    import app.config as config_module

    importlib.reload(config_module)
    importlib.reload(es_module)

    # Stub OpenAI client call
    dummy = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="AI result"))]
    )

    async def fake_create(*args, **kwargs):
        return dummy

    # 🚨 Correct patch target!
    monkeypatch.setattr(es_module.openai_client.chat.completions, "create", fake_create)

    email = EmailMessageBase(
        subject="Subj", body="Body text", sender="user@example.com"
    )

    result = await es_module.generate_summary(email)

    # ✅ Now this assertion makes sense
    assert result == "AI result"
