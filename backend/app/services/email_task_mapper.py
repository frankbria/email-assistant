# app/services/email_task_mapper.py

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
from app.models.email_message import EmailMessage, EmailMessageBase
from app.models.assistant_task import AssistantTask
import app.services.context_classifier as context_classifier
from app.services.email_summarizer import generate_summary
from app.services.action_suggester import suggest_actions
from app.utils.email_utils import parse_forwarded_metadata
from .duplicate_detection import is_spam_email


async def handle_spam_email(email: EmailMessage):
    """Handles spam emails by marking them as spam and skipping task creation."""
    email.is_spam = True
    await email.save()  # Persist the spam status in the database
    return None  # Skip task creation


async def map_email_to_task(
    email: EmailMessage,
    actions: Optional[List[str]] = None,
    skipSpamCheck: bool = False,
    forceFullProcessing: bool = False,
) -> Optional[AssistantTask]:
    """
    Map an EmailMessage to an AssistantTask.

    Args:
        email: The EmailMessage to map
        actions: Optional list of actions
        skipSpamCheck: Skip spam check (for emails marked as not spam)
        forceFullProcessing: Force full AI processing regardless of other conditions

    Returns:
        An AssistantTask object or None if the email is spam and skipSpamCheck is False
    """
    if not skipSpamCheck and is_spam_email(email):
        return await handle_spam_email(email)

    if forceFullProcessing or not email.is_spam:

        logger.debug("🔄 Mapping email to task in service")
        print("Mapping email to task in service")
        # Try to extract original sender/subject from forwarded content
        forwarded_sender, forwarded_subject = parse_forwarded_metadata(email.body)
        # Treat empty strings as None for fallback logic
        forwarded_sender = (
            forwarded_sender if forwarded_sender and forwarded_sender.strip() else None
        )
        forwarded_subject = (
            forwarded_subject
            if forwarded_subject and forwarded_subject.strip()
            else None
        )
        # Determine sender and subject defaults, with warnings if missing
        if forwarded_sender:
            sender_val = forwarded_sender
        else:
            if not email.sender or not email.sender.strip():
                logger.warning(
                    "EmailMessage missing sender; defaulting to 'Unknown Sender'"
                )
            sender_val = (
                email.sender.strip()
                if email.sender and email.sender.strip()
                else "Unknown Sender"
            )
        if forwarded_subject:
            subject_val = forwarded_subject
        else:
            if not email.subject or not email.subject.strip():
                logger.warning(
                    "EmailMessage missing subject; defaulting to '(No Subject)'"
                )
            subject_val = (
                email.subject.strip()
                if email.subject and email.subject.strip()
                else "(No Subject)"
            )
        logger.debug("🔄 Classifying context")
        # Classify context using AI or rule-based
        context_label = await context_classifier.classify_context(
            subject_val, email.body
        )
        logger.debug("🔄 Generating summary")
        # Generate summary: handle long bodies and missing subjects before AI/rule-based
        body_text = email.body.strip() if email.body else ""
        if body_text:
            # Long body truncation
            if len(body_text) > 100:
                snippet = await generate_summary(
                    EmailMessageBase(
                        subject=subject_val,
                        body=body_text[:100] + "…",
                        sender=email.sender,
                    )
                )
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

        logger.debug("🔄 Suggesting actions")
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

        logger.debug("🔄 Building task kwargs")
        # Build task with all collected data
        task_kwargs = {
            "email": email,
            "sender": sender_val,
            "subject": subject_val,
            "context": context_label,
            "summary": summary_text,
            "user_id": email.user_id,
            "actions": actions,
        }
        task = AssistantTask(**task_kwargs)
    return task
