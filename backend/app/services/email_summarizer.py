# backend/app/services/email_summarizer.py

import os
import logging
from pydantic import BaseModel
from app.models.email_message import EmailMessageBase
from app.services.ai_client import ai_logger
from app.services.ai_provider import get_ai_provider
from app.utils.email_utils import is_generic_subject, extract_first_sentence

logger = logging.getLogger(__name__)


class TaskSummary(BaseModel):
    summary: str


async def generate_summary(email: EmailMessageBase) -> str:
    """
    Generates a concise, actionable summary of an email by:
    1. Using AI summarization if enabled,
    2. Falling back to smart heuristics if AI is unavailable.
    """
    use_ai_summary = os.getenv("USE_AI_SUMMARY", "false").lower() == "true"

    if use_ai_summary:
        prompt = (
            "Summarize this email into one short, actionable task description. "
            "Focus on what the owner is being asked to do or consider. "
            "Be specific and concise.\n\n"
            f"Subject: {email.subject or '(No Subject)'}\n"
            f"Body: {email.body or '(No Body)'}"
        )
        try:
            result = await get_ai_provider().propose(prompt, TaskSummary)
            if result.summary.strip():
                return result.summary.strip()
        except Exception as error:
            ai_logger.error(f"AI summarization failed: {error}")

    # Non-AI fallback path
    if not email.subject and not email.body:
        return "No content available"

    if email.subject and not is_generic_subject(email.subject):
        return f"Handle: {email.subject}"

    if email.body:
        first_sentence = extract_first_sentence(email.body)
        if first_sentence:
            return f"Follow up: {first_sentence}"

    return "Task from incoming email"
