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


def parse_forwarded_metadata(body: str):
    """
    Parses forwarded email content to extract the original sender and subject.
    Returns (original_sender, original_subject) or (None, None) if not found.
    Handles common 'From:' and 'Subject:' patterns in the body.
    """
    if not body:
        return None, None
    # Regex for common forwarded email headers (match up to end of line)
    from_pattern = re.compile(r"^From:\s*(.*)$", re.MULTILINE)
    subject_pattern = re.compile(r"^Subject:\s*(.*)$", re.MULTILINE)
    # Find all matches
    from_matches = from_pattern.findall(body)
    subject_matches = subject_pattern.findall(body)

    # Use the first non-empty, non-header match if available
    def valid_value(val):
        val = val.strip()
        return val and not val.startswith("Subject:") and not val.startswith("From:")

    original_sender = (
        from_matches[0].strip()
        if from_matches and valid_value(from_matches[0])
        else None
    )
    original_subject = (
        subject_matches[0].strip()
        if subject_matches and valid_value(subject_matches[0])
        else None
    )
    return original_sender, original_subject


def parse_forwarded_email_body(body: str):
    """
    Parses the body of a forwarded email to extract the original content.
    This function is a placeholder and should be implemented based on specific needs.
    """
    if not body:
        return ""
    # Example: Remove common forward indicators
    body = re.sub(r"^-----Original Message-----.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^From:.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^Sent:.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^To:.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^Subject:.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^---.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^On.*wrote:", "", body, flags=re.DOTALL)
    body = re.sub(r"^-----.*", "", body, flags=re.DOTALL)
    body = re.sub(r"^>.*", "", body, flags=re.DOTALL)
    body = re.sub(r"\n{2,}", "\n", body)  # Remove excessive newlines
    body = body.strip()  # Clean up leading/trailing whitespace
    # Return the cleaned body

    return body
