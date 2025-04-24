# backend/app/strategies/email_actions.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class ReplyStrategy(ActionStrategy):
    """Strategy for reply-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Quick Reply", action_type="reply", handler="handle_quick_reply"
            ),
            SuggestedAction(
                label="Reply with Template",
                action_type="template_reply",
                handler="handle_template_reply",
            ),
            SuggestedAction(
                label="Reply All", action_type="reply_all", handler="handle_reply_all"
            ),
        ]


class ForwardStrategy(ActionStrategy):
    """Strategy for forwarding-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Forward", action_type="forward", handler="handle_forward"
            ),
            SuggestedAction(
                label="Forward with Note",
                action_type="forward_note",
                handler="handle_forward_note",
            ),
        ]


class NotificationStrategy(ActionStrategy):
    """Strategy for notification-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Notify Team",
                action_type="notify_team",
                handler="handle_notify_team",
            ),
            SuggestedAction(
                label="Escalate", action_type="escalate", handler="handle_escalate"
            ),
            SuggestedAction(
                label="Set Reminder", action_type="reminder", handler="handle_reminder"
            ),
        ]


# Register strategies
ActionRegistry.register("default", ReplyStrategy)
ActionRegistry.register("default", ForwardStrategy)
ActionRegistry.register("default", NotificationStrategy)
ActionRegistry.register(
    "support", NotificationStrategy
)  # Also used for support tickets
