# backend/app/models/assistant_task.py

from beanie import Document, WriteRules, Link
from pydantic import Field, model_validator
from typing import Optional, List
from app.models.email_message import EmailMessage
from pymongo import IndexModel, ASCENDING


class AssistantTask(Document):
    email: Link[EmailMessage]
    sender: Optional[str] = None
    subject: Optional[str] = None
    context: Optional[str] = None
    summary: Optional[str] = None
    actions: List[str] = Field(default_factory=lambda: ["Reply", "Forward", "Archive"])
    status: str = Field(default="pending")
    user_id: str = Field(description="ID of the user who owns this task")
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

    @model_validator(mode="after")
    def ensure_consistent_user_id(self) -> "AssistantTask":
        """
        After validation, ensure user_id matches the linked email's user_id
        """
        if hasattr(self, "email") and hasattr(self.email, "user_id"):
            self.user_id = self.email.user_id
        return self

    class Settings:
        name = "assistant_tasks"
        link_rule = WriteRules.WRITE
        indexes = [IndexModel([("user_id", ASCENDING)])]  # Corrected index format
