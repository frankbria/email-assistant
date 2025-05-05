# backend/app/services/duplicate_detection.py

import hashlib
from difflib import SequenceMatcher
from typing import Optional
import json
from pathlib import Path

from app.models.email_message import EmailMessage
from app.config import get_settings

# Load spam keywords from a JSON file
SPAM_KEYWORDS_FILE = Path(__file__).parent / "spam_keywords.json"


# Placeholder function for spam detection
def is_spam_email(email: EmailMessage) -> bool:
    """Detects if an email is spam based on keywords."""
    try:
        with open(SPAM_KEYWORDS_FILE, "r") as f:
            spam_keywords = json.load(f)
    except FileNotFoundError:
        spam_keywords = []

    # Check if any spam keyword is in the email subject or body
    email_content = f"{email.subject} {email.body}".lower()
    return any(keyword.lower() in email_content for keyword in spam_keywords)


async def is_duplicate_email(email: EmailMessage) -> bool:
    """
    Returns True if duplicate, False otherwise.
    Attaches signature to email if unique.
    """
    # 1) message_id exact match
    if email.message_id:
        existing = await EmailMessage.find_one(
            EmailMessage.message_id == email.message_id
        )
        if existing:
            return True

    # 2) compute exact content signature
    hash_input = (email.sender + email.subject + email.body).encode("utf-8")
    exact_sig = hashlib.sha256(hash_input).hexdigest()
    existing = await EmailMessage.find_one(EmailMessage.signature == exact_sig)
    if existing:
        return True

    # 3) fuzzy match subject+body against recent emails
    #    (you may want to limit the query scope by time or user)
    recent = await EmailMessage.find().limit(100).to_list()
    for other in recent:
        subj_sim = SequenceMatcher(
            None, email.subject or "", other.subject or ""
        ).ratio()
        body_sim = SequenceMatcher(None, email.body or "", other.body or "").ratio()
        if ((subj_sim + body_sim) / 2) >= get_settings().duplicate_threshold:
            return True

    # unique — attach exact signature and proceed
    email.signature = exact_sig
    return False
