# backend/app/services/duplicate_detection.py

import json
from pathlib import Path

from app.models.email_message import EmailMessage

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
