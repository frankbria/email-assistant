# app/services/email_task_mapper.py

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
import app.services.context_classifier as context_classifier


async def map_email_to_task(
    email: EmailMessage,
    actions: Optional[List[str]] = None,
) -> AssistantTask:
    """
    Create an AssistantTask from an EmailMessage, centralizing defaults, classification, and summary logic.
    Does not insert the task into the database; caller should insert it.
    """
    # Determine sender and subject defaults, with warnings if missing
    if not email.sender or not email.sender.strip():
        logger.warning("EmailMessage missing sender; defaulting to 'Unknown Sender'")
    sender_val = (
        email.sender.strip()
        if email.sender and email.sender.strip()
        else "Unknown Sender"
    )
    if not email.subject or not email.subject.strip():
        logger.warning("EmailMessage missing subject; defaulting to '(No Subject)'")
    subject_val = (
        email.subject.strip()
        if email.subject and email.subject.strip()
        else "(No Subject)"
    )
    # Classify context using AI or rule-based
    context_label = await context_classifier.classify_context(subject_val, email.body)

    # Build summary: use subject_val if body empty, else subject_val + truncated snippet
    trimmed = email.body.strip() if email.body else ""
    if not trimmed:
        summary_text = subject_val
    else:
        snippet = trimmed[:100] + ("…" if len(trimmed) > 100 else "")
        summary_text = f"{subject_val}: {snippet}"

    # Build kwargs dynamically so default actions kick in when actions is None
    task_kwargs = {
        "email": email,
        "sender": sender_val,
        "subject": subject_val,
        "context": context_label,
        "summary": summary_text,
    }
    if actions is not None:
        task_kwargs["actions"] = actions
    task = AssistantTask(**task_kwargs)
    return task
