# backend/app/strategies/sales.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class SalesStrategy(ActionStrategy):
    """Strategy for suggesting sales-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Schedule Demo", action_type="demo", handler="handle_demo"
            ),
            SuggestedAction(
                label="Send Pricing", action_type="pricing", handler="handle_pricing"
            ),
        ]


# Register strategy
ActionRegistry.register("sales", SalesStrategy)
