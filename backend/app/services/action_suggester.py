# backend/app/services/action_suggester.py

from typing import List, Protocol
from pydantic import BaseModel
from app.models.email_message import EmailMessageBase


class SuggestedAction(BaseModel):
    """Represents a suggested action for an email task"""

    label: str
    action_type: str
    handler: str  # Name of the handler function to call


class ActionStrategy(Protocol):
    """Protocol defining the interface for action strategies"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        """Generate suggested actions based on the email context"""
        ...


def suggest_actions(email: EmailMessageBase) -> List[SuggestedAction]:
    """
    Suggests appropriate actions based on the email's context.
    Returns a list of 2-3 relevant actions for the given context.
    """
    from app.strategies.action_registry import ActionRegistry

    # Get context-specific strategies or default to generic ones
    strategies = (
        ActionRegistry.get_strategies(email.context)
        or ActionRegistry.get_default_strategies()
    )

    # Collect actions from all applicable strategies
    actions: List[SuggestedAction] = []
    for strategy_class in strategies:
        strategy = strategy_class()
        actions.extend(strategy.get_actions(email))

    # Ensure we have at least 2 actions
    if len(actions) < 2:
        default_strategies = ActionRegistry.get_default_strategies()
        for strategy_class in default_strategies:
            strategy = strategy_class()
            actions.extend(strategy.get_actions(email))
            if len(actions) >= 2:
                break

    return actions[:3]  # Return at most 3 actions
