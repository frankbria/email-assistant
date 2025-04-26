# backend/app/services/email_summarizer.py

import os
import re
from typing import Optional
from app.models.email_message import EmailMessageBase
from app.config import get_settings
from app.services.ai_client import openai_client, OPENAI_MODEL, logger as ai_logger
import openai


def is_generic_subject(subject: str) -> bool:
    """Determines if a subject line is too generic to be used as a summary."""
    generic_patterns = [
        r"^re:",
        r"^fw:",
        r"^fwd:",
        r"^follow up$",
        r"^quick question$",
        r"^hi$",
        r"^hello$",
        r"^thanks$",
        r"^thank you$",
        r"^update$",
    ]
    subject = subject.lower().strip()
    return any(re.match(pattern, subject) for pattern in generic_patterns)


def extract_first_sentence(text: str) -> Optional[str]:
    """Extracts the first complete sentence from a text block."""
    if not text:
        return None

    # Remove greeting prefixes
    text = re.sub(
        r"^(hi|hello|dear|thanks|thank you)[,\s]+", "", text, flags=re.IGNORECASE
    )

    # Find first full sentence
    sentence_match = re.search(r"^(.+?[.!?])(?:\s|$)", text)
    if sentence_match:
        return sentence_match.group(1).strip()

    # Fallback: first line
    first_line = text.split("\n")[0].strip()
    return first_line if first_line else None


async def generate_summary(email: EmailMessageBase) -> str:
    """
    Generates a concise summary of an email by:
    1. Using AI summarization if enabled,
    2. Falling back to smart heuristics.
    """
    # ❗ Dynamically recheck environment at runtime
    use_ai_summary = os.getenv("USE_AI_SUMMARY", "false").lower() == "true"

    if use_ai_summary and openai_client:
        try:
            prompt = f"Summarize the following email in one concise sentence:\nSubject: {email.subject}\nBody: {email.body}"
            print("🔄 Sending summary prompt to OpenAI: ", prompt)
            response = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant that summarizes emails.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            summary = response.choices[0].message.content.strip()
            if summary:
                print("✅ Received AI summary: ", summary)
                return summary
        except Exception as e:
            ai_logger.error(f"AI summarization failed: {e}")
            print("🔄 AI summarization failed: ", e)

    # Non-AI fallback path
    if not email.subject and not email.body:
        return "No content available"

    if email.subject and not is_generic_subject(email.subject):
        return email.subject

    if email.body:
        first_sentence = extract_first_sentence(email.body)
        if first_sentence:
            return first_sentence

    return email.subject or "No content available"
