# backend/app/models/assistant_task.py

from beanie import Document
from pydantic import Field, model_validator
from typing import Optional, List
from app.models.email_message import EmailMessage


class AssistantTask(Document):
    email: EmailMessage = Field(...)
    sender: Optional[str] = None
    subject: Optional[str] = None
    context: Optional[str] = None
    summary: Optional[str] = None
    actions: List[str] = Field(default_factory=lambda: ["Reply", "Forward", "Archive"])
    status: str = Field(default="pending")
    action_taken: Optional[str] = Field(
        default=None, description="The action that was taken to complete this task"
    )

    @model_validator(mode="after")
    def validate_status(self) -> "AssistantTask":
        valid_statuses = ["pending", "in_progress", "done", "archived"]
        if self.status not in valid_statuses:
            self.status = "pending"
        return self

    @model_validator(mode="after")
    def ensure_default_actions(self) -> "AssistantTask":
        if not self.actions:
            self.actions = ["Reply", "Forward", "Archive"]
        return self

    @model_validator(mode="after")
    def populate_sender_subject(self) -> "AssistantTask":
        """
        After validation, ensure sender and subject default from the linked email if unset.
        """
        # Default sender from email if not provided
        if not self.sender and hasattr(self, "email"):
            self.sender = self.email.sender
        # Default subject from email if not provided
        if not self.subject and hasattr(self, "email"):
            self.subject = self.email.subject
        return self

    class Settings:
        name = "assistant_tasks"
