# backend/app/services/action_suggester.py

from typing import List, Protocol
import logging
from pydantic import BaseModel
from app.models.email_message import EmailMessageBase
from app.config import get_settings
from app.services.ai_client import openai_client

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


async def suggest_actions_ai(email: EmailMessageBase) -> List[SuggestedAction]:
    """
    Use OpenAI to suggest actions based on email content and context.
    Returns AI-generated actions or None if AI fails.
    """
    if not openai_client:
        return None

    try:
        # Construct prompt for action suggestion
        system_prompt = """You are an AI assistant that suggests actions for handling emails.
For each email, suggest 2-3 relevant actions based on the content and context.
Each action should have:
1. A clear label (e.g. "Schedule Meeting", "Forward to Team")
2. An action_type (e.g. "schedule", "forward")
3. A handler name (e.g. "handle_schedule", "handle_forward")

Format your response as a JSON array of objects with these exact keys: label, action_type, handler
Example: [{"label": "Schedule Meeting", "action_type": "schedule", "handler": "handle_schedule"}]"""

        user_prompt = f"""Subject: {email.subject}
Body: {email.body}
Context: {email.context if hasattr(email, 'context') else 'unknown'}

Suggest 2-3 relevant actions for handling this email."""

        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        # Parse response and convert to SuggestedAction objects
        actions_data = response.choices[0].message.content
        if isinstance(actions_data, str):
            import json

            actions_data = json.loads(actions_data)

        actions = []
        for action in actions_data.get("actions", []):
            try:
                actions.append(SuggestedAction(**action))
            except Exception as e:
                logger.warning(f"Failed to parse AI action: {e}")
                continue

        if actions:
            return actions[:3]

    except Exception as e:
        logger.error(f"AI action suggestion failed: {e}")

    return None


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
            ActionRegistry.get_strategies(email.context)
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
