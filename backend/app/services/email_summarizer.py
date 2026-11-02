# backend/app/services/email_summarizer.py

import os
import logging
from app.models.email_message import EmailMessageBase
from app.services.ai_client import openai_client, OPENAI_MODEL, ai_logger
from app.utils.email_utils import is_generic_subject, extract_first_sentence

logger = logging.getLogger(__name__)


async def generate_summary(email: EmailMessageBase) -> str:
    """
    Generates a concise, actionable summary of an email by:
    1. Using AI summarization if enabled,
    2. Falling back to smart heuristics if AI is unavailable.
    """
    use_ai_summary = os.getenv("USE_AI_SUMMARY", "false").lower() == "true"

    if use_ai_summary and openai_client:
        try:
            prompt = (
                "You are an executive assistant. "
                "Summarize the following email into one short, actionable task description. "
                "Focus on what the user is being asked to do or consider. "
                "Avoid vague language. Be specific and concise.\n\n"
                f"Subject: {email.subject or '(No Subject)'}\n"
                f"Body: {email.body or '(No Body)'}"
            )
            logger.debug("🔄 Sending summary prompt to OpenAI: ", prompt)
            response = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an executive assistant helping summarize emails into tasks.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            summary = (response.choices[0].message.content or "").strip()
            if summary:
                logger.debug("✅ Received AI-generated task summary: ", summary)
                return summary
        except Exception as e:
            ai_logger.error(f"AI summarization failed: {e}")
            logger.debug("⚠️ AI summarization failed, falling back: ", e)

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
