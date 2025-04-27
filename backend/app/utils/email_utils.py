import re


def is_generic_subject(subject: str) -> bool:
    """
    Determines if a subject line is too generic to be used as a summary.
    Generic subjects are short, common phrases that don't convey specific meaning.
    """
    if not subject:
        return True
    generic_patterns = [
        r"^re:",
        r"^fw:",
        r"^fwd:",  # Common email prefixes
        r"^follow up$",
        r"^quick question$",
        r"^hi$",
        r"^hello$",
    ]
    for pattern in generic_patterns:
        if re.match(pattern, subject.strip(), re.IGNORECASE):
            return True
    return False


def extract_first_sentence(text: str) -> str:
    """
    Extracts the first meaningful sentence from a block of text.
    """
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in sentences:
        if sentence and len(sentence.split()) >= 3:  # Filter out tiny fragments
            return sentence.strip()
    return text.strip()  # Fall back to whole text if no sentence found
