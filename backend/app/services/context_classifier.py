# backend/app/services/context_classifier.py

import os
import logging

from app.models.email_message import EmailMessageBase
from app.services.ai_client import classify_context_ai
from app.services.task_classifier import classify_context as classify_context_rule

# Determine mode via environment variable
USE_AI = os.getenv("USE_AI_CONTEXT", "false").lower() in ("true", "1", "yes")

logger = logging.getLogger(__name__)


async def classify_context(subject: str, body: str) -> str:
    """
    Unified context classifier. If USE_AI_CONTEXT is enabled, delegates to AI-based classifier;
    otherwise or on error, falls back to rule-based classifier.
    """
    logger.debug("🔄 Classifying context in service")
    if USE_AI:
        try:
            logger.debug("🔄 Using AI classifier")
            return await classify_context_ai(subject, body)
        except Exception as e:
            logging.error(f"AI classification error, falling back to rule-based: {e}")
            logger.debug("🔄 Falling back to rule-based classifier")
    # Fallback to rule-based classification
    email = EmailMessageBase(subject=subject, body=body, sender="")
    return classify_context_rule(email)
