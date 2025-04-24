# backend/app/models/email_message.py
from typing import Optional
from pydantic import BaseModel, Field
from beanie import Document


class EmailMessageBase(BaseModel):
    """Base Pydantic model for email messages that can be used in tests"""

    subject: str
    body: str
    sender: str
    recipient: Optional[str] = None
    context: Optional[str] = None


class EmailMessage(Document, EmailMessageBase):
    """Beanie Document model for MongoDB storage"""

    class Settings:
        name = "email_messages"
