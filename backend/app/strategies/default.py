# backend/app/strategies/default.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class DefaultEmailStrategy(ActionStrategy):
    """Default strategy for basic email actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(label="Reply", action_type="reply", handler="handle_reply"),
            SuggestedAction(
                label="Forward", action_type="forward", handler="handle_forward"
            ),
            SuggestedAction(
                label="Archive", action_type="archive", handler="handle_archive"
            ),
        ]


# Register as default strategy
ActionRegistry.register("default", DefaultEmailStrategy)
