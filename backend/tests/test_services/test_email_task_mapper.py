import pytest

from app.services.email_task_mapper import map_email_to_task
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

# Prevent Beanie from requiring DB initialization in tests
EmailMessage.get_motor_collection = lambda self: None
AssistantTask.get_motor_collection = lambda self: None

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

    email = EmailMessage(subject="Hello", sender="Alice", body="World")
    task = await map_email_to_task(email)

    assert isinstance(task, AssistantTask)
    assert task.sender == "Alice"
    assert task.subject == "Hello"
    assert task.context == "mocked_context"
    assert task.summary == "Hello: World"
    # Default actions should be set by the model validator
    assert task.actions == ["Reply", "Forward", "Archive"]


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
