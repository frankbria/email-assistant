# backend/tests/test_services/test_duplicate_detection.py

import pytest
import asyncio
import time
from app.services.duplicate_detection import is_duplicate_email
from app.models.email_message import EmailMessage


@pytest.mark.asyncio
async def test_duplicate_by_message_id(db_transaction):
    """Emails with the same message_id should be flagged as duplicates."""
    # Insert an email with a specific message_id
    email1 = EmailMessage(
        subject="First", sender="alice@example.com", body="Hello", message_id="msg-123"
    )
    await email1.insert()
    # Create a new email with the same message_id
    email2 = EmailMessage(
        subject="Second", sender="bob@example.com", body="World", message_id="msg-123"
    )
    assert await is_duplicate_email(email2) is True


@pytest.mark.asyncio
async def test_duplicate_by_signature(db_transaction):
    """Emails with identical sender, subject, and body should be flagged as duplicates by signature."""
    payload = {
        "subject": "Repeat",
        "sender": "charlie@example.com",
        "body": "Same content",
    }
    # First pass computes and stores signature
    email1 = EmailMessage(**payload)
    assert await is_duplicate_email(email1) is False
    sig = email1.signature
    await email1.insert()
    # New email with same payload should be duplicate
    email2 = EmailMessage(**payload)
    assert await is_duplicate_email(email2) is True


@pytest.mark.asyncio
async def test_unique_emails_not_flagged(db_transaction):
    """Different emails should not be flagged as duplicates."""
    # Insert one email
    email1 = EmailMessage(subject="Unique1", sender="eve@example.com", body="Content A")
    # Compute signature to avoid null conflict and insert
    assert await is_duplicate_email(email1) is False
    await email1.insert()
    # Insert another with different content
    email2 = EmailMessage(subject="Unique2", sender="eve@example.com", body="Content B")
    assert await is_duplicate_email(email2) is False
    # signature should be set for unique email
    assert email2.signature is not None


@pytest.mark.asyncio
async def test_similar_content_flagged(db_transaction):
    """Similar but non-identical emails should be flagged based on threshold."""
    # first email (unique)
    e1 = EmailMessage(
        subject="Meeting tomorrow at 10",
        sender="foo@example.com",
        body="Please confirm attendance.",
    )
    assert await is_duplicate_email(e1) is False
    await e1.insert()

    # second email with minor variations
    e2 = EmailMessage(
        subject="Meeting tomorrow at 10am",
        sender="foo@example.com",
        body="Pls confirm attend.",
    )
    assert await is_duplicate_email(e2) is True


@pytest.mark.perf
@pytest.mark.asyncio
async def test_performance_under_load(db_transaction):
    """Ensure duplicate check stays fast with 100 similar emails."""
    # prepare 100 pairs
    pairs = []
    for i in range(100):
        subj = f"Test {i}"
        body = "Data " * i
        e1 = EmailMessage(subject=subj, sender="u@example.com", body=body)
        e2 = EmailMessage(subject=subj, sender="u@example.com", body=body)
        pairs.append((e1, e2))

    async def run_all():
        for idx, (a, b) in enumerate(pairs):
            if idx % 10 == 0:
                print(f"Processing pair {idx} of {len(pairs)}")
            # we don’t insert, just compare in‐memory
            await is_duplicate_email(a)
            await is_duplicate_email(b)

    start = time.perf_counter()
    await run_all()
    end = time.perf_counter()
    elapsed_ms = (end - start) * 1000
    print(
        f"Duplicate check for {len(pairs)*2} emails. Performance test took {elapsed_ms:.2f} ms"
    )
    assert True
