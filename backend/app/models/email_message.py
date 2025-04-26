# backend/app/models/email_message.py
from typing import Optional
from pydantic import BaseModel
from beanie import Document


class EmailMessageBase(BaseModel):
    subject: str
    sender: str
    body: str
    recipient: Optional[str] = None
    context: Optional[str] = None


class EmailMessage(Document):
    subject: str
    sender: str
    body: str
    recipient: Optional[str] = None
    context: Optional[str] = None

    class Settings:
        name = "email_messages"
