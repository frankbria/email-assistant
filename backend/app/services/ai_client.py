# backend/app/services/ai_client.py

import logging
import os
from typing import Literal, get_args

from pydantic import BaseModel

from app.services.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger("ai_client")

Category = Literal["scheduling", "sales", "support", "partner", "personal", "other"]
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(Category))


class ContextClassification(BaseModel):
    category: Category


async def classify_context_ai(subject: str, body: str) -> str:
    """
    Classifies the email into one of _VALID_CATEGORIES through the AI provider.
    Returns 'other' when AI classification is disabled or fails.
    """
    if os.getenv("USE_AI_CONTEXT", "false").lower() != "true":
        return "other"

    prompt = (
        "Classify this email into exactly one category: "
        f"{', '.join(sorted(_VALID_CATEGORIES))}.\n\n"
        f"Subject: {subject}\n\nBody: {body}"
    )
    try:
        result = await get_ai_provider().propose(prompt, ContextClassification)
    except Exception as error:
        logger.error(f"AI classification failed: {error}")
        return "other"
    return result.category
