# backend/app/strategies/scheduling.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class ScheduleMeetingStrategy(ActionStrategy):
    """Strategy for suggesting meeting-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Schedule Meeting",
                action_type="schedule",
                handler="handle_schedule",
            ),
            SuggestedAction(
                label="Decline Meeting", action_type="decline", handler="handle_decline"
            ),
            SuggestedAction(
                label="Propose New Time",
                action_type="reschedule",
                handler="handle_reschedule",
            ),
        ]


class ScheduleCallStrategy(ActionStrategy):
    """Strategy for suggesting call-related actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Schedule Call", action_type="call", handler="handle_call"
            ),
            SuggestedAction(
                label="Send Calendar Link",
                action_type="calendar",
                handler="handle_calendar",
            ),
        ]


# Register strategies
ActionRegistry.register("scheduling", ScheduleMeetingStrategy)
ActionRegistry.register("scheduling", ScheduleCallStrategy)
ActionRegistry.register(
    "partner", ScheduleCallStrategy
)  # Also used for partner meetings
