# backend/app/services/ai_client.py

import os
import openai
import logging

logger = logging.getLogger(__name__)
from typing import Set

# Load OpenAI credentials from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_API_MODEL", "gpt-3.5-turbo")

# Configure OpenAI client if key is present, otherwise log a warning
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logger.warning(
        "Missing OPENAI_API_KEY environment variable; AI classification will always return 'other'"
    )

# Allowed categories for classification
_VALID_CATEGORIES: Set[str] = {
    "scheduling",
    "sales",
    "support",
    "partner",
    "personal",
    "other",
}


async def classify_context_ai(subject: str, body: str) -> str:
    """
    Uses OpenAI to classify the email into one of the predefined categories:
    scheduling, sales, support, partner, personal, or other.
    Returns the category label in lowercase; defaults to 'other' on error or invalid response.
    """
    # (Removed early exit to ensure AI method and logging are exercised)

    # Dynamically create category list for the system prompt
    categories_str = ", ".join(sorted(_VALID_CATEGORIES))
    system_prompt = (
        f"You are an AI assistant that classifies emails into one of the following categories: {categories_str}. "
        "Respond with only the category label (one of these) in lowercase."
    )
    user_prompt = f"Subject: {subject}\n\nBody: {body}"

    try:
        response = await openai.ChatCompletion.acreate(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        category = response.choices[0].message.content.strip().lower()
    except Exception as e:
        logger.error(f"AI classification failed: {e}")
        return "other"

    if category not in _VALID_CATEGORIES:
        logger.warning(
            f"Received unexpected category '{category}', defaulting to 'other'."
        )
        return "other"

    return category
