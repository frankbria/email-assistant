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

    @model_validator(mode="after")
    def ensure_default_actions(self) -> "AssistantTask":
        if not self.actions:
            self.actions = ["Reply", "Forward", "Archive"]
        return self

    class Settings:
        name = "assistant_tasks"
