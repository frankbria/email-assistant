# backend/tests/test_services/test_email_to_task_conversion.py

import pytest
from pydantic import ValidationError

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.email_task_mapper import map_email_to_task
from app.utils.email_utils import parse_forwarded_metadata


@pytest.mark.asyncio
async def test_basic_email_to_task_conversion(db_transaction):
    """Test that a basic email is correctly converted to a task with all required fields."""
    # Create a test email with all fields populated
    email = EmailMessage(
        subject="Important update on project timeline",
        sender="john.doe@example.com",
        body="We need to discuss the project timeline. There have been some delays.",
        user_id="test_user",
        is_spam=False,
    )
    await email.insert()

    # Convert email to task
    task = await map_email_to_task(email)

    # Verify task creation was successful
    assert task is not None

    # Verify task has the correct fields from the email
    assert task.email.id == email.id
    assert task.sender == email.sender
    assert task.subject == email.subject
    assert task.user_id == email.user_id

    # Verify derived fields
    assert task.summary is not None
    assert task.context is not None
    assert isinstance(task.actions, list)
    assert len(task.actions) > 0
    assert task.status == "pending"  # Default status
    assert task.action_taken is None  # No action taken yet


@pytest.mark.asyncio
async def test_email_to_task_with_missing_fields(db_transaction):
    """Test that an email with missing fields is converted to a task with appropriate defaults."""
    # Create a test email with minimal fields
    email = EmailMessage(
        user_id="test_user",
    )
    await email.insert()

    # Convert email to task
    task = await map_email_to_task(email)

    # Verify task creation was successful
    assert task is not None

    # Verify task has appropriate defaults for missing fields
    assert task.sender == "Unknown Sender"
    assert task.subject == "(No Subject)"
    assert task.user_id == email.user_id

    # Verify derived fields still exist
    assert task.summary is not None
    assert isinstance(task.actions, list)
    assert len(task.actions) > 0


@pytest.mark.asyncio
async def test_email_to_task_with_custom_actions(db_transaction):
    """Test that custom actions are respected when provided."""
    # Create a test email
    email = EmailMessage(
        subject="Product inquiry",
        sender="customer@example.com",
        body="I'm interested in your product. Can you send me more information?",
        user_id="test_user",
    )
    await email.insert()

    # Custom actions to pass
    custom_actions = ["Send Info", "Schedule Demo", "Add to CRM"]

    # Convert email to task with custom actions
    task = await map_email_to_task(email, actions=custom_actions)

    # Verify task creation was successful
    assert task is not None

    # Verify custom actions are used
    assert task.actions == custom_actions


@pytest.mark.asyncio
async def test_forwarded_email_to_task(db_transaction):
    """Test that forwarded emails are properly processed with original sender and subject."""
    # Create a test forwarded email
    forwarded_content = """
    ---------- Forwarded message ---------
    From: Jane Smith <jane.smith@example.com>
    Subject: Original Request
    Date: Wed, 1 May 2025 10:00:00 -0700
    
    Can you please review the attached proposal and provide feedback?
    """

    email = EmailMessage(
        subject="Fwd: Original Request",
        sender="john.doe@example.com",
        body=forwarded_content,
        user_id="test_user",
    )
    await email.insert()

    # Convert email to task
    task = await map_email_to_task(email)

    # Verify task creation was successful
    assert task is not None

    # Verify forwarded metadata is extracted and used
    forwarded_sender, forwarded_subject = parse_forwarded_metadata(email.body)
    assert task.sender == forwarded_sender
    assert task.subject == forwarded_subject

    # Double-check the original values
    assert forwarded_sender == "Jane Smith <jane.smith@example.com>"
    assert forwarded_subject == "Original Request"


@pytest.mark.asyncio
async def test_user_id_preservation_in_task(db_transaction):
    """Test that user_id is correctly preserved when mapping email to task."""
    # Create emails with different user IDs
    user_ids = ["user1", "user2", "user3"]

    for user_id in user_ids:
        email = EmailMessage(
            subject=f"Test for {user_id}",
            sender=f"{user_id}@example.com",
            body=f"Test email body for {user_id}",
            user_id=user_id,
        )
        await email.insert()

        # Convert email to task
        task = await map_email_to_task(email)

        # Verify task user_id matches email user_id
        assert task.user_id == user_id


@pytest.mark.asyncio
async def test_task_can_be_persisted(db_transaction):
    """Test that the created task can be properly persisted to the database."""
    # Create a test email
    email = EmailMessage(
        subject="Meeting Request",
        sender="colleague@example.com",
        body="Can we meet tomorrow to discuss the project?",
        user_id="test_user",
    )
    await email.insert()

    # Convert email to task
    task = await map_email_to_task(email)

    # Insert task into the database
    await task.insert()

    # Retrieve task from database
    retrieved_task = await AssistantTask.get(task.id)

    # Verify retrieved task matches created task
    assert retrieved_task.id == task.id
    assert retrieved_task.sender == task.sender
    assert retrieved_task.subject == task.subject
    assert retrieved_task.summary == task.summary
    assert retrieved_task.context == task.context
    assert retrieved_task.actions == task.actions
    assert retrieved_task.user_id == task.user_id


@pytest.mark.asyncio
async def test_long_email_body_summary(db_transaction):
    """Test that long email bodies are properly summarized."""
    # Create a test email with a long body
    long_body = (
        "This is a very long email body. " * 30
    )  # Repeats to create long content

    email = EmailMessage(
        subject="Long Email Test",
        sender="verbose@example.com",
        body=long_body,
        user_id="test_user",
    )
    await email.insert()

    # Convert email to task
    task = await map_email_to_task(email)

    # Verify task creation was successful
    assert task is not None

    # Verify summary is not the entire body
    assert len(task.summary) < len(long_body)
    # Summary should still contain the subject
    assert "Long Email Test" in task.summary
