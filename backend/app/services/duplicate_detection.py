# backend/app/services/duplicate_detection.py

import hashlib
from difflib import SequenceMatcher
from typing import Optional

from app.models.email_message import EmailMessage
from backend.app.config import DUPLICATE_THRESHOLD


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
        if ((subj_sim + body_sim) / 2) >= DUPLICATE_THRESHOLD:
            return True

    # unique — attach exact signature and proceed
    email.signature = exact_sig
    return False
