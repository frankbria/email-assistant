# backend/tests/test_services/test_malformed_emails.py

import pytest
from app.models.email_message import EmailMessage
from app.services.email_task_mapper import map_email_to_task


@pytest.mark.asyncio
async def test_empty_sender_defaults_to_unknown_sender(db_transaction):
    """Test that an email with empty sender is mapped to a task with 'Unknown Sender'."""
    # Create an email with empty sender
    email = EmailMessage(
        subject="Test Subject",
        sender="",  # Empty sender
        body="This is a test email with an empty sender field.",
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify defaults were applied correctly
    assert task.sender == "Unknown Sender"
    assert task.subject == "Test Subject"
    assert task.summary is not None
    assert "Unknown Sender" in task.summary or task.summary.startswith("Test Subject:")


@pytest.mark.asyncio
async def test_empty_subject_defaults_to_no_subject(db_transaction):
    """Test that an email with empty subject is mapped to a task with '(No Subject)'."""
    # Create an email with empty subject
    email = EmailMessage(
        subject="",  # Empty subject
        sender="test@example.com",
        body="This is a test email with an empty subject field.",
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify defaults were applied correctly
    assert task.sender == "test@example.com"
    assert task.subject == "(No Subject)"
    assert task.summary is not None
    assert task.summary.startswith("(No Subject):")


@pytest.mark.asyncio
async def test_empty_body_handling(db_transaction):
    """Test that an email with empty body is handled gracefully."""
    # Create an email with empty body
    email = EmailMessage(
        subject="Test Subject",
        sender="test@example.com",
        body="",  # Empty body
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify defaults were applied correctly
    assert task.sender == "test@example.com"
    assert task.subject == "Test Subject"
    assert task.summary == "Test Subject"  # Should just use subject when body is empty
    assert task.context is not None  # Context should still be classified


@pytest.mark.asyncio
async def test_minimal_email_all_defaults(db_transaction):
    """Test that a minimal email with all empty fields is handled with defaults."""
    # Create a minimal email with all empty fields (except required user_id)
    email = EmailMessage(subject="", sender="", body="", user_id="test_user_id")
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify all defaults were applied correctly
    assert task.sender == "Unknown Sender"
    assert task.subject == "(No Subject)"
    assert task.summary == "(No Subject)"
    assert task.actions == ["Reply", "Forward", "Archive"]  # Default actions


@pytest.mark.asyncio
async def test_whitespace_only_fields(db_transaction):
    """Test that fields with only whitespace are treated as empty."""
    # Create an email with whitespace-only fields
    email = EmailMessage(
        subject="  \t\n  ",  # Whitespace only
        sender="  \t\n  ",  # Whitespace only
        body="  \t\n  ",  # Whitespace only
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify defaults were applied correctly
    assert task.sender == "Unknown Sender"
    assert task.subject == "(No Subject)"
    assert task.summary == "(No Subject)"


@pytest.mark.asyncio
async def test_extremely_long_body_truncation(db_transaction):
    """Test that extremely long email bodies are properly truncated in the summary."""
    # Create an email with a very long body
    long_body = "This is a very long email body. " * 100  # Repeats 100 times
    email = EmailMessage(
        subject="Long Email",
        sender="test@example.com",
        body=long_body,
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify the summary is reasonable in length
    assert task.summary is not None
    assert task.summary.startswith("Long Email:")
    assert len(task.summary) <= 200  # Reasonable summary length


@pytest.mark.asyncio
async def test_malformed_email_with_custom_actions(db_transaction):
    """Test that a malformed email with custom actions retains those actions."""
    # Create a malformed email
    email = EmailMessage(subject="", sender="", body="", user_id="test_user_id")
    await email.insert()

    # Define custom actions
    custom_actions = ["Approve", "Reject", "Defer"]

    # Map the email to a task with custom actions
    task = await map_email_to_task(email, actions=custom_actions)

    # Verify defaults were applied but custom actions were retained
    assert task.sender == "Unknown Sender"
    assert task.subject == "(No Subject)"
    assert task.actions == custom_actions  # Custom actions should be kept


@pytest.mark.asyncio
async def test_special_characters_in_fields(db_transaction):
    """Test that emails with special characters are handled properly."""
    # Create an email with special characters
    email = EmailMessage(
        subject="Tést Sübject 👋 #$%^&*",
        sender="test+special@example.com",
        body="Test body with emojis 🚀 and special chars: ©®™µ€£¥",
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify special characters are preserved
    assert task.sender == "test+special@example.com"
    assert task.subject == "Tést Sübject 👋 #$%^&*"
    assert task.summary is not None
    assert task.summary.startswith("Tést Sübject 👋")


@pytest.mark.asyncio
async def test_forwarded_email_with_missing_metadata(db_transaction):
    """Test that forwarded emails without clear metadata are handled properly."""
    # Create a malformed forwarded email without clear metadata
    email = EmailMessage(
        subject="Fwd:",  # Empty forwarded subject
        sender="forwarder@example.com",
        body="""
        ---------- Forwarded message ---------
        
        Text without proper metadata format
        
        Some email content here
        """,
        user_id="test_user_id",
    )
    await email.insert()

    # Map the email to a task
    task = await map_email_to_task(email)

    # Verify defaults and proper handling
    assert (
        task.sender == "forwarder@example.com"
    )  # Should use actual sender as fallback
    assert task.subject == "Fwd:"  # Should preserve the forwarded prefix
