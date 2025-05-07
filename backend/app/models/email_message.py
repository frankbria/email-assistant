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
    user_id: str = Field(description="ID of the user who owns this email")
    is_spam: bool = Field(
        default=False, description="Indicates if the email is flagged as spam."
    )
    is_archived: bool = Field(
        default=False, description="Indicates if the email is archived."
    )

    class Settings:
        name = "email_messages"
        indexes = [
            IndexModel([("subject", ASCENDING), ("sender", ASCENDING)]),
            IndexModel([("signature", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
        ]
