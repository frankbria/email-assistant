# backend/tests/test_services/test_action_suggester.py
import pytest
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import (
    suggest_actions,
    ActionStrategy,
    SuggestedAction,
)
from app.strategies.action_registry import ActionRegistry


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
        ]


@pytest.fixture(autouse=True)
def setup_strategies():
    """Setup mock strategies for testing"""
    # Clear existing strategies
    ActionRegistry._strategies.clear()

    # Register mock strategies
    ActionRegistry.register("scheduling", MockSchedulingStrategy)
    ActionRegistry.register("sales", MockSalesStrategy)
    ActionRegistry.register("default", MockDefaultStrategy)

    yield

    # Cleanup
    ActionRegistry._strategies.clear()


def test_suggest_actions_for_scheduling():
    """
    Validates that scheduling-related emails get appropriate action suggestions.
    This test ensures the basic action mapping works for a clear-cut case.
    """
    email = EmailMessageBase(
        subject="Meeting Request: Project Kickoff",
        body="Hi, I'd like to schedule a meeting to discuss the project kickoff. Please let me know your availability.",
        sender="test@example.com",
        context="scheduling",
    )
    actions = suggest_actions(email)
    assert len(actions) >= 2, "Should suggest at least 2 actions"
    assert any(
        "Schedule" in action.label for action in actions
    ), "Should include scheduling action"
    assert any(
        "Decline" in action.label for action in actions
    ), "Should include decline option"


def test_suggest_actions_for_sales():
    """
    Validates that sales-related emails get appropriate action suggestions.
    This test ensures different contexts get different action sets.
    """
    email = EmailMessageBase(
        subject="Product Inquiry",
        body="I'm interested in learning more about your pricing plans",
        sender="prospect@example.com",
        context="sales",
    )
    actions = suggest_actions(email)
    assert len(actions) >= 2, "Should suggest at least 2 actions"
    assert any(
        "Schedule Demo" in action.label for action in actions
    ), "Should include demo scheduling"
    assert any(
        "Send Pricing" in action.label for action in actions
    ), "Should include pricing info"


def test_suggest_actions_for_unknown_context():
    """
    Validates that emails with unknown contexts get default action suggestions.
    This test ensures graceful handling of edge cases.
    """
    email = EmailMessageBase(
        subject="Random Email",
        body="This is a test email",
        sender="test@example.com",
        context="unknown",
    )
    actions = suggest_actions(email)
    assert len(actions) >= 2, "Should suggest at least 2 actions"
    assert any(
        "Reply" in action.label for action in actions
    ), "Should include basic reply option"
    assert any(
        "Forward" in action.label for action in actions
    ), "Should include basic forward option"
