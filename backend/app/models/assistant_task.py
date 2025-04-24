# backend/app/models/assistant_task.py
from beanie import Document
from pydantic import Field
from typing import Optional, List
from app.models.email_message import EmailMessage


class AssistantTask(Document):
    email: EmailMessage = Field(...)
    context: Optional[str] = None
    summary: Optional[str] = None
    suggested_actions: List[str] = Field(default_factory=list)
    status: str = Field(default="pending")

    class Settings:
        name = "assistant_tasks"
