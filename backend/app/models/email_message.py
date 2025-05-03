# backend/app/models/email_message.py
from typing import Optional
from pydantic import BaseModel, Field
from beanie import Document
from pymongo import IndexModel, ASCENDING


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
    message_id: Optional[str] = Field(None)
    signature: Optional[str] = Field(None)

    class Settings:
        name = "email_messages"
        indexes = [
            IndexModel([("subject", ASCENDING), ("sender", ASCENDING)]),
            IndexModel([("signature", ASCENDING)]),
        ]
