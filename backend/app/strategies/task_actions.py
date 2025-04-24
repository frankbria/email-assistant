# backend/app/strategies/task_actions.py
from typing import List
from app.models.email_message import EmailMessageBase
from app.services.action_suggester import ActionStrategy, SuggestedAction
from app.strategies.action_registry import ActionRegistry


class TaskCompletionStrategy(ActionStrategy):
    """Strategy for task completion actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Mark Complete", action_type="complete", handler="handle_complete"
            ),
            SuggestedAction(
                label="Mark In Progress",
                action_type="in_progress",
                handler="handle_in_progress",
            ),
            SuggestedAction(
                label="Add to Project",
                action_type="add_to_project",
                handler="handle_add_to_project",
            ),
        ]


class TaskDelayStrategy(ActionStrategy):
    """Strategy for task delay and scheduling actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Delay 1 Day", action_type="delay_1d", handler="handle_delay_1d"
            ),
            SuggestedAction(
                label="Delay 1 Week", action_type="delay_1w", handler="handle_delay_1w"
            ),
            SuggestedAction(
                label="Schedule for Later",
                action_type="schedule_later",
                handler="handle_schedule_later",
            ),
        ]


class TaskIgnoreStrategy(ActionStrategy):
    """Strategy for task ignore and archive actions"""

    def get_actions(self, email: EmailMessageBase) -> List[SuggestedAction]:
        return [
            SuggestedAction(
                label="Ignore", action_type="ignore", handler="handle_ignore"
            ),
            SuggestedAction(
                label="Archive", action_type="archive", handler="handle_archive"
            ),
            SuggestedAction(
                label="Snooze", action_type="snooze", handler="handle_snooze"
            ),
        ]


# Register strategies
ActionRegistry.register("default", TaskCompletionStrategy)
ActionRegistry.register("default", TaskDelayStrategy)
ActionRegistry.register("default", TaskIgnoreStrategy)
ActionRegistry.register("personal", TaskIgnoreStrategy)  # Also used for personal emails
