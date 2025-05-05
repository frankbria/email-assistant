import pytest

from app.services.email_task_mapper import map_email_to_task
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.strategies.action_registry import ActionRegistry
from app.strategies.default import DefaultEmailStrategy
from app.config import Settings

pytestmark = pytest.mark.asyncio


async def test_full_mapping_and_defaults(monkeypatch):
    """
    Given a normal email, map_email_to_task should return an AssistantTask with
    correct sender, subject, context, summary, and default actions.
    """

    # Stub classifier to return a known context
    async def fake_classify(subject, body):
        return "mocked_context"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=False),
    )

    from app.strategies.default import DefaultEmailStrategy
    from app.strategies.action_registry import ActionRegistry

    ActionRegistry._strategies.clear()
    ActionRegistry.register("default", DefaultEmailStrategy)

    email = EmailMessage(subject="Hello", sender="Alice", body="World")
    task = await map_email_to_task(email)

    assert isinstance(task, AssistantTask)
    assert task.sender == "Alice"
    assert task.subject == "Hello"
    assert task.context == "mocked_context"
    assert task.summary == "Hello: Follow up: World"

    # Default actions should be set by the model validator
    labels = task.actions
    assert "Reply" in labels
    assert "Archive" in labels
    assert "Forward" in labels


async def test_summary_truncation(monkeypatch):
    """
    Body longer than 100 chars should be truncated with an ellipsis.
    """

    async def fake_classify2(subject, body):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify2,
    )
    long_body = "A" * 150
    email = EmailMessage(subject="Subj", sender="Bob", body=long_body)
    task = await map_email_to_task(email)

    assert task.summary.startswith("Subj: ")
    # After 'Subj: ' check 100 'A's and an ellipsis
    expected_snippet = "A" * 100 + "…"
    assert expected_snippet in task.summary


async def test_missing_sender_and_subject(monkeypatch):
    """
    When sender or subject is empty, defaults should be applied.
    """

    async def fake_classify3(s, b):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify3,
    )
    # Empty sender and subject
    email = EmailMessage(subject="   ", sender="", body="Body text")
    task = await map_email_to_task(email)

    assert task.sender == "Unknown Sender"
    assert task.subject == "(No Subject)"
    # Summary uses the defaulted subject
    assert task.summary.startswith("(No Subject): Body text")


async def test_empty_body_summary(monkeypatch):
    """
    When body is empty, summary should equal the subject.
    """

    async def fake_classify4(s, b):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify4,
    )
    email = EmailMessage(subject="TestSubj", sender="Eve", body="  ")
    task = await map_email_to_task(email)

    assert task.summary == "TestSubj"


async def test_custom_actions(monkeypatch):
    """
    Passing a custom actions list should override the defaults.
    """

    async def fake_classify5(s, b):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify5,
    )
    email = EmailMessage(subject="S", sender="U", body="B")
    custom_actions = ["Action1", "Action2"]
    task = await map_email_to_task(email, actions=custom_actions)

    assert task.actions == custom_actions


@pytest.mark.asyncio
async def test_forwarded_email_parsing(monkeypatch):
    """
    When the email body contains forwarded headers, the original sender and subject are extracted.
    """

    async def fake_classify(subject, body):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )
    body = """Some intro text
From: Jane Doe <jane@example.com>
Subject: Original Subject Line
Body: This is the original message body.
"""
    email = EmailMessage(
        subject="Fwd: See below", sender="forwarder@example.com", body=body
    )
    task = await map_email_to_task(email)
    assert task.sender == "Jane Doe <jane@example.com>"
    assert task.subject == "Original Subject Line"


@pytest.mark.asyncio
async def test_forwarded_email_fallback(monkeypatch):
    """
    If no forwarded headers are found, fallback to the forwarding user's metadata.
    """

    async def fake_classify(subject, body):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )
    body = "No forwarded headers here."
    email = EmailMessage(subject="No Fwd", sender="forwarder@example.com", body=body)
    task = await map_email_to_task(email)
    assert task.sender == "forwarder@example.com"
    assert task.subject == "No Fwd"


@pytest.mark.asyncio
async def test_forwarded_email_multiple_fields(monkeypatch):
    """
    If multiple From:/Subject: fields are present, use the first instance.
    """

    async def fake_classify(subject, body):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )
    body = """From: First Sender <first@example.com>
Subject: First Subject
From: Second Sender <second@example.com>
Subject: Second Subject
"""
    email = EmailMessage(
        subject="Fwd: Multi", sender="forwarder@example.com", body=body
    )
    task = await map_email_to_task(email)
    assert task.sender == "First Sender <first@example.com>"
    assert task.subject == "First Subject"


@pytest.mark.asyncio
async def test_forwarded_email_malformed_fields(monkeypatch):
    """
    Malformed or partial forwarded headers should not crash and should fallback gracefully.
    """

    async def fake_classify(subject, body):
        return "ctx"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )
    body = """From: 
Subject:  """
    email = EmailMessage(
        subject="Fwd: Malformed", sender="forwarder@example.com", body=body
    )
    task = await map_email_to_task(email)

    assert task.sender == "forwarder@example.com"
    assert task.subject == "Fwd: Malformed"


@pytest.mark.asyncio
async def test_map_email_to_task_skips_spam():
    email = EmailMessage(
        subject="Win a prize",
        body="Click here to claim your free money",
        sender="test@example.com",
    )
    task = await map_email_to_task(email)
    assert task is None
    assert email.is_spam is True


@pytest.mark.asyncio
async def test_map_email_to_task_creates_task_for_non_spam():
    email = EmailMessage(
        subject="Meeting tomorrow",
        body="Let's discuss the project updates",
        sender="test@example.com",
    )
    task = await map_email_to_task(email)
    assert task is not None
    assert email.is_spam is False
