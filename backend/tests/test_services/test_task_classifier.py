# backend/tests/test_services/test_task_classifier.py
import pytest
from app.models.email_message import EmailMessageBase
from app.services.task_classifier import classify_context


def test_classify_scheduling_request():
    """
    Validates that an email containing scheduling-related keywords
    is correctly classified as a scheduling task.
    This test ensures the basic keyword matching functionality works
    for a clear-cut case.
    """
    email = EmailMessageBase(
        subject="Meeting Request",
        body="Hi, would you like to schedule a meeting next week?",
        sender="test@example.com",
    )
    category = classify_context(email)
    assert (
        category == "scheduling"
    ), "Email with scheduling keywords should be classified as scheduling"


def test_classify_sales_inquiry():
    """
    Validates that an email containing sales-related keywords
    is correctly classified as a sales task.
    This test ensures the classifier can identify different categories
    based on distinct keyword sets.
    """
    email = EmailMessageBase(
        subject="Product Inquiry",
        body="I'm interested in learning more about your pricing plans",
        sender="prospect@example.com",
    )
    category = classify_context(email)
    assert (
        category == "sales"
    ), "Email with sales keywords should be classified as sales"


def test_classify_mixed_content():
    """
    Validates that an email containing keywords from multiple categories
    is classified based on the most prominent category.
    This test ensures the classifier can handle ambiguous cases
    and make a reasonable decision.
    """
    email = EmailMessageBase(
        subject="Follow up on our meeting",
        body="Thanks for the demo yesterday. Can we schedule another call to discuss pricing?",
        sender="client@example.com",
    )
    category = classify_context(email)
    assert category in [
        "scheduling",
        "sales",
    ], "Mixed content should be classified as either scheduling or sales"
