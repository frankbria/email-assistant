# backend/app/models/assistant_task.py
from beanie import Document, Link
from pydantic import Field
from .email_message import EmailMessage


class AssistantTask(Document):
    email: Link[EmailMessage]
    # Add more fields as needed (e.g., context, summary, actions)
