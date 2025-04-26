# backend/app/services/email_summarizer.py
import re
from typing import Optional
from app.models.email_message import EmailMessageBase
from app.config import get_settings
from app.services.ai_client import OPENAI_MODEL, logger as ai_logger, openai


def is_generic_subject(subject: str) -> bool:
    """
    Determines if a subject line is too generic to be used as a summary.
    Generic subjects are short, common phrases that don't convey specific meaning.
    """
    generic_patterns = [
        r"^re:",
        r"^fw:",
        r"^fwd:",  # Common email prefixes
        r"^follow up$",
        r"^quick question$",
        r"^hi$",
        r"^hello$",  # Generic phrases
        r"^thanks$",
        r"^thank you$",
        r"^update$",  # More generic phrases
    ]
    subject = subject.lower().strip()
    return any(re.match(pattern, subject) for pattern in generic_patterns)


def extract_first_sentence(text: str) -> Optional[str]:
    """
    Extracts the first complete sentence from a text block.
    Handles common sentence endings and ignores common email prefixes.
    Preserves the sentence-ending punctuation.
    """
    if not text:
        return None

    # Remove common email prefixes
    text = re.sub(
        r"^(hi|hello|dear|thanks|thank you)[,\s]+", "", text, flags=re.IGNORECASE
    )

    # Find the first sentence including its ending punctuation
    sentence_match = re.search(r"^(.+?[.!?])(?:\s|$)", text)
    if sentence_match:
        return sentence_match.group(1).strip()

    # If no sentence-ending punctuation found, return the first line
    first_line = text.split("\n")[0].strip()
    return first_line if first_line else None


async def generate_summary(email: EmailMessageBase) -> str:
    """
    Generates a concise summary of an email by either:
    1. Using the subject if it's descriptive enough
    2. Extracting the first meaningful sentence from the body
    3. Returning a default message if no content is available
    4. Optionally delegating to AI summarization when enabled
    """
    settings = get_settings()
    # AI-based summarization
    if settings.use_ai_summary:
        try:
            # system prompt for summarization
            prompt = f"Summarize the following email in one concise sentence:\nSubject: {email.subject}\nBody: {email.body}"
            response = await openai.ChatCompletion.acreate(
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
                return summary
        except Exception as e:
            ai_logger.error(f"AI summarization failed: {e}")
    # Handle empty content
    if not email.subject and not email.body:
        return "No content available"

    # Use subject if it's descriptive
    if email.subject and not is_generic_subject(email.subject):
        return email.subject

    # Extract first sentence from body
    if email.body:
        first_sentence = extract_first_sentence(email.body)
        if first_sentence:
            return first_sentence

    # Fallback to subject if body extraction failed
    return email.subject or "No content available"
