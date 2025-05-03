import hashlib
from app.models.email_message import EmailMessage
from typing import Optional


async def is_duplicate_email(email: EmailMessage) -> bool:
    """
    Check if the given email is a duplicate based on message_id or content signature.
    Returns True if duplicate, False otherwise, and attaches signature to email if unique.
    """
    # Use message_id for duplicate check if provided
    if email.message_id:
        existing = await EmailMessage.find_one(
            EmailMessage.message_id == email.message_id
        )
        if existing:
            return True

    # Compute a signature hash from sender, subject, and body
    hash_input = (email.sender + email.subject + email.body).encode("utf-8")
    signature = hashlib.sha256(hash_input).hexdigest()

    # Check for existing email with the same signature
    existing = await EmailMessage.find_one(EmailMessage.signature == signature)
    if existing:
        return True

    # Attach signature for later insertion
    email.signature = signature
    return False
