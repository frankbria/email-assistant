# backend/tests/test_services/test_action_suggester.py

import pytest
import json
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import (
    suggest_actions,
    suggest_actions_ai,
    ActionStrategy,
    SuggestedAction,
)
from app.strategies.action_registry import ActionRegistry
from app.config import Settings
from tests.utils.fakes import mock_openai_response

pytestmark = pytest.mark.asyncio

# Mock email for testing
TEST_EMAIL = EmailMessageBase(
    subject="Meeting Request",
    body="Can we schedule a meeting next week?",
    sender="test@example.com",
    context="scheduling",
)

# Mock AI response data (now correct)
MOCK_AI_ACTIONS = {
    "actions": [
        {
            "label": "Schedule Meeting",
            "action_type": "schedule",
            "handler": "handle_schedule",
        },
        {"label": "Reply", "action_type": "reply", "handler": "handle_reply"},
    ]
}


class MockSchedulingStrategy(ActionStrategy):
    def get_actions(self, email: EmailMessageBase) -> list[SuggestedAction]:
        return [
            SuggestedAction(
                label="Schedule Meeting",
                action_type="schedule",
                handler="handle_schedule",
            ),
            SuggestedAction(
                label="Decline Meeting", action_type="decline", handler="handle_decline"
            ),
        ]


class MockSalesStrategy(ActionStrategy):
    def get_actions(self, email: EmailMessageBase) -> list[SuggestedAction]:
        return [
            SuggestedAction(
                label="Schedule Demo", action_type="demo", handler="handle_demo"
            ),
            SuggestedAction(
                label="Send Pricing", action_type="pricing", handler="handle_pricing"
            ),
        ]


class MockDefaultStrategy(ActionStrategy):
    def get_actions(self, email: EmailMessageBase) -> list[SuggestedAction]:
        return [
            SuggestedAction(label="Reply", action_type="reply", handler="handle_reply"),
            SuggestedAction(
                label="Forward", action_type="forward", handler="handle_forward"
            ),
            SuggestedAction(
                label="Archive", action_type="archive", handler="handle_archive"
            ),
        ]


@pytest.fixture(autouse=True)
def setup_strategies():
    """Setup mock strategies for testing."""
    ActionRegistry._strategies.clear()
    ActionRegistry._default_strategies = [MockDefaultStrategy]
    ActionRegistry.register("scheduling", MockSchedulingStrategy)
    ActionRegistry.register("sales", MockSalesStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)
    yield
    ActionRegistry._strategies.clear()


async def test_suggest_actions_for_scheduling(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    ActionRegistry._strategies.clear()
    ActionRegistry.register("scheduling", MockSchedulingStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)
    email = EmailMessageBase(
        subject="Meeting Request: Project Kickoff",
        body="Let's schedule the kickoff meeting next week.",
        sender="test@example.com",
        context="scheduling",
    )
    actions = await suggest_actions(email)
    assert len(actions) >= 2
    assert any("Schedule" in action.label for action in actions)
    assert any("Decline" in action.label for action in actions)


async def test_suggest_actions_for_sales(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    ActionRegistry._strategies.clear()
    ActionRegistry.register("sales", MockSalesStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)
    email = EmailMessageBase(
        subject="Product Inquiry",
        body="I'm interested in learning more about your pricing plans.",
        sender="prospect@example.com",
        context="sales",
    )
    actions = await suggest_actions(email)
    assert len(actions) >= 2
    assert any("Schedule Demo" in action.label for action in actions)
    assert any("Send Pricing" in action.label for action in actions)


async def test_suggest_actions_for_unknown_context(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    ActionRegistry._strategies.clear()
    ActionRegistry.register("default", MockDefaultStrategy)
    email = EmailMessageBase(
        subject="Random Email",
        body="This is a test email",
        sender="test@example.com",
        context="unknown",
    )
    actions = await suggest_actions(email)
    assert len(actions) >= 2
    assert any("Reply" in action.label for action in actions)
    assert any("Forward" in action.label for action in actions)


async def test_suggest_actions_ai_success(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(json.dumps(MOCK_AI_ACTIONS)),
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=True),
    )

    actions = await suggest_actions_ai(TEST_EMAIL)
    assert actions is not None
    assert len(actions) == 2
    assert isinstance(actions[0], SuggestedAction)
    assert actions[0].label == "Schedule Meeting"
    assert actions[0].action_type == "schedule"
    assert actions[0].handler == "handle_schedule"


async def test_suggest_actions_ai_failure(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(exception=Exception("API Error")),
    )
    actions = await suggest_actions_ai(TEST_EMAIL)
    assert actions is None


async def test_suggest_actions_with_ai_enabled(monkeypatch):
    class MockSettings(Settings):
        use_ai_actions: bool = True

    monkeypatch.setattr(
        "app.services.action_suggester.get_settings", lambda: MockSettings()
    )
    monkeypatch.setattr(
        "app.config.get_settings", lambda: Settings(use_ai_actions=True)
    )

    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(json.dumps(MOCK_AI_ACTIONS)),
    )

    actions = await suggest_actions(TEST_EMAIL)
    assert len(actions) >= 2
    assert actions[0].label == "Schedule Meeting"


async def test_suggest_actions_fallback_to_rule_based(monkeypatch):
    monkeypatch.setattr(
        "app.services.action_suggester.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(use_ai_actions=False),
    )
    ActionRegistry._strategies.clear()
    ActionRegistry.register("scheduling", MockSchedulingStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)
    actions = await suggest_actions(TEST_EMAIL)
    assert len(actions) >= 2
    labels = [action.label for action in actions]
    assert "Schedule Meeting" in labels or "Reply" in labels
    assert "Decline Meeting" in labels or "Forward" in labels


async def test_suggest_actions_ensures_minimum_actions(monkeypatch):
    class MockSettings(Settings):
        use_ai_actions: bool = False

    monkeypatch.setattr(
        "app.services.action_suggester.get_settings", lambda: MockSettings()
    )
    monkeypatch.setattr("app.config.get_settings", lambda: MockSettings())
    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(json.dumps(MOCK_AI_ACTIONS)),
    )

    class MockStrategy:
        def get_actions(self, email):
            return [
                SuggestedAction(
                    label="Reply", action_type="reply", handler="handle_reply"
                ),
            ]

    class MockDefaultStrategy:
        def get_actions(self, email):
            return [
                SuggestedAction(
                    label="Forward", action_type="forward", handler="handle_forward"
                ),
            ]

    ActionRegistry._strategies.clear()
    ActionRegistry.register("unknown", MockStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)
    email = EmailMessageBase(
        subject="Fallback Test",
        body="Trigger fallback to default strategies",
        sender="fallback@example.com",
        context="unknown",
    )
    actions = await suggest_actions(email)
    assert len(actions) >= 2
    labels = [action.label for action in actions]
    assert "Reply" in labels or "Forward" in labels
