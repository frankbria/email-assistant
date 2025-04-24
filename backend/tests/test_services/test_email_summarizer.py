# backend/tests/test_services/test_email_summarizer.py
import pytest
from app.models.email_message import EmailMessageBase
from app.services.email_summarizer import generate_summary


def test_generate_summary_from_subject():
    """
    Validates that when the subject clearly describes the email's purpose,
    it is used as the summary.
    This test ensures we don't overcomplicate when the subject is sufficient.
    """
    email = EmailMessageBase(
        subject="Meeting Request: Project Kickoff",
        body="Hi, I'd like to schedule a meeting to discuss the project kickoff. Please let me know your availability.",
        sender="test@example.com",
    )
    summary = generate_summary(email)
    assert (
        summary == "Meeting Request: Project Kickoff"
    ), "Clear subject should be used as summary"


def test_generate_summary_from_body():
    """
    Validates that when the subject is generic, the first meaningful sentence
    from the body is used as the summary.
    This test ensures we extract relevant information when the subject isn't descriptive.
    """
    email = EmailMessageBase(
        subject="Follow up",
        body="I'm writing to request a demo of your product next week. We're particularly interested in the enterprise features.",
        sender="prospect@example.com",
    )
    summary = generate_summary(email)
    assert (
        summary == "I'm writing to request a demo of your product next week."
    ), "First meaningful sentence should be used as summary"


def test_generate_summary_empty_content():
    """
    Validates that the summarizer handles empty or invalid content gracefully.
    This test ensures the service doesn't break with edge cases.
    """
    email = EmailMessageBase(subject="", body="", sender="test@example.com")
    summary = generate_summary(email)
    assert (
        summary == "No content available"
    ), "Empty content should return a default message"
