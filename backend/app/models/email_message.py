# backend/app/models/email_message.py
from beanie import Document
from pydantic import Field


class EmailMessage(Document):
    subject: str = Field(...)
    sender: str
    body: str
