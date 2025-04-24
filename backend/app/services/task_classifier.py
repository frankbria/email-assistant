from typing import Dict, List
from app.models.email_message import EmailMessageBase

# Define categories and their associated keywords
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "scheduling": [
        "meeting",
        "schedule",
        "calendar",
        "call",
        "appointment",
        "time slot",
        "availability",
        "book a time",
    ],
    "sales": [
        "pricing",
        "quote",
        "demo",
        "trial",
        "purchase",
        "product",
        "service",
        "cost",
        "price",
        "buy",
    ],
    "support": [
        "help",
        "issue",
        "problem",
        "error",
        "bug",
        "ticket",
        "support",
        "assistance",
        "question",
    ],
    "partner": [
        "partnership",
        "collaboration",
        "joint",
        "alliance",
        "cooperation",
        "work together",
        "team up",
    ],
    "personal": [
        "thank you",
        "congratulations",
        "welcome",
        "hello",
        "hi",
        "greetings",
        "personal",
        "catch up",
    ],
}


def classify_context(email: EmailMessageBase) -> str:
    """
    Classifies an email into one of the predefined categories based on keyword matching.
    Returns the category with the highest match count, or 'other' if no matches are found.
    """
    # Combine subject and body for analysis
    text = f"{email.subject} {email.body}".lower()

    # Count matches for each category
    match_counts: Dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        match_counts[category] = sum(1 for keyword in keywords if keyword in text)

    # Find category with most matches
    max_matches = max(match_counts.values())
    if max_matches == 0:
        return "other"

    # Return first category with max matches (in case of tie)
    return next(
        category for category, count in match_counts.items() if count == max_matches
    )
