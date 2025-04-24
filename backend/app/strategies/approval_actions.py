# backend/app/strategies/approval_actions.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class ApprovalStrategy(ActionStrategy):
    """Strategy for approval and review actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Approve", action_type="approve", handler="handle_approve"
            ),
            SuggestedAction(
                label="Reject", action_type="reject", handler="handle_reject"
            ),
            SuggestedAction(
                label="Request Changes",
                action_type="request_changes",
                handler="handle_request_changes",
            ),
        ]


class ReviewStrategy(ActionStrategy):
    """Strategy for review and feedback actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Review", action_type="review", handler="handle_review"
            ),
            SuggestedAction(
                label="Add Comments",
                action_type="add_comments",
                handler="handle_add_comments",
            ),
            SuggestedAction(
                label="Request Review",
                action_type="request_review",
                handler="handle_request_review",
            ),
        ]


# Register strategies
ActionRegistry.register("default", ApprovalStrategy)
ActionRegistry.register("default", ReviewStrategy)
ActionRegistry.register(
    "partner", ApprovalStrategy
)  # Also used for partner communications
ActionRegistry.register("sales", ReviewStrategy)  # Also used for sales proposals
