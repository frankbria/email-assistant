# backend/app/services/action_suggester.py

from typing import List, Protocol
import logging
from pydantic import BaseModel
from app.models.email_message import EmailMessageBase
from app.config import get_settings
from app.services.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


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


class ActionSuggestions(BaseModel):
    actions: List[SuggestedAction]


async def suggest_actions_ai(email: EmailMessageBase) -> List[SuggestedAction] | None:
    """
    Asks the AI provider for up to 3 actions for the email.
    Returns None when the AI fails or suggests nothing.
    """
    prompt = f"""Suggest 3 relevant actions for handling this email.
Each action has a clear label (e.g. "Schedule Meeting"), an action_type (e.g. "schedule")
and a handler name (e.g. "handle_schedule"). Meetings should include a schedule,
forward, and decline option.

Subject: {email.subject}
Body: {email.body}
Context: {email.context or 'unknown'}"""
    try:
        result = await get_ai_provider().propose(prompt, ActionSuggestions)
    except Exception as error:
        logger.error(f"AI action suggestion failed: {error}")
        return None
    return result.actions[:3] or None


async def suggest_actions(email: EmailMessageBase) -> List[SuggestedAction]:
    """
    Suggests appropriate actions based on the email's context.
    Uses AI suggestions if enabled, falls back to rule-based strategies.
    Guarantees returning 2-3 relevant actions.
    """
    settings = get_settings()

    actions: List[SuggestedAction] = []

    # 1. Try AI first if enabled
    if settings.use_ai_actions:
        ai_actions = await suggest_actions_ai(email)
        if ai_actions:
            actions.extend(ai_actions)

    # 2. If AI is disabled or fails, use rule-based strategies
    if not actions:

        from app.strategies.action_registry import ActionRegistry

        # Try context-specific strategies first
        strategies = (
            (email.context and ActionRegistry.get_strategies(email.context))
            or ActionRegistry.get_default_strategies()
        )

        for strategy_class in strategies:
            strategy = strategy_class()
            actions.extend(strategy.get_actions(email))

    # 3. If STILL not enough actions, force add defaults
    if len(actions) < 3:
        from app.strategies.default import DefaultEmailStrategy

        default_strategy = DefaultEmailStrategy()
        default_actions = default_strategy.get_actions(email)

        # Only add missing ones
        existing_labels = {action.label for action in actions}
        for default_action in default_actions:
            if default_action.label not in existing_labels:
                actions.append(default_action)
            if len(actions) >= 3:
                break

    return actions[:3]  # Always return max 3 actions
