# app/services/email_task_mapper.py

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
from app.models.email_message import EmailMessage, EmailMessageBase
from app.models.assistant_task import AssistantTask
import app.services.context_classifier as context_classifier
from app.services.email_summarizer import generate_summary
from app.services.action_suggester import suggest_actions


async def map_email_to_task(
    email: EmailMessage,
    actions: Optional[List[str]] = None,
) -> AssistantTask:
    """
    Create an AssistantTask from an EmailMessage, centralizing defaults, classification, and summary logic.
    Does not insert the task into the database; caller should insert it.
    """
    print("🔄 Mapping email to task in service")
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
    print("🔄 Classifying context")
    # Classify context using AI or rule-based
    context_label = await context_classifier.classify_context(subject_val, email.body)
    print("🔄 Generating summary")
    # Generate summary: handle long bodies and missing subjects before AI/rule-based
    body_text = email.body.strip() if email.body else ""
    if body_text:
        # Long body truncation
        if len(body_text) > 100:
            snippet = body_text[:100] + "…"
        # Missing subject default: use full body as snippet
        elif subject_val == "(No Subject)":
            snippet = body_text
        else:
            # use AI or rule-based summarizer for concise snippet
            snippet = await generate_summary(
                EmailMessageBase(
                    subject=subject_val, body=email.body, sender=email.sender
                )
            )
        summary_text = f"{subject_val}: {snippet}" if snippet else subject_val
    else:
        summary_text = subject_val

    print("🔄 Suggesting actions")
    # Get suggested actions if not provided
    if actions is None:
        try:
            suggested_actions = await suggest_actions(
                EmailMessageBase(
                    subject=subject_val,
                    body=email.body,
                    sender=sender_val,
                    context=context_label,
                )
            )
            actions = [action.label for action in suggested_actions]
        except Exception as e:
            logger.error(f"Error suggesting actions: {e}")
            actions = ["Reply", "Forward", "Archive"]  # fallback or default action

    print("🔄 Building task kwargs")
    # Build task with all collected data
    task_kwargs = {
        "email": email,
        "sender": sender_val,
        "subject": subject_val,
        "context": context_label,
        "summary": summary_text,
        "actions": actions,
    }
    task = AssistantTask(**task_kwargs)
    return task
