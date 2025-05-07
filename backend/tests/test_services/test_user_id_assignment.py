# backend/tests/test_services/test_user_id_assignment.py

import pytest
from beanie import PydanticObjectId

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.email_task_mapper import map_email_to_task
from app.config import get_settings


@pytest.mark.asyncio
async def test_email_creation_assigns_user_id(db_transaction):
    """Test that creating an EmailMessage always assigns a user_id."""
    # Create a test email without explicitly setting user_id
    email = EmailMessage(
        subject="Test Subject",
        sender="test@example.com",
        body="This is a test email body",
    )
    await email.insert()

    # Retrieve the email from the database
    inserted_email = await EmailMessage.get(email.id)

    # Verify user_id is assigned and matches the default
    assert inserted_email.user_id is not None
    assert inserted_email.user_id == get_settings().DEFAULT_USER_ID


@pytest.mark.asyncio
async def test_task_creation_assigns_user_id(db_transaction):
    """Test that creating an AssistantTask always assigns a user_id."""
    # Create a test email with a specific user_id
    test_user_id = "test_user"
    email = EmailMessage(
        subject="Test Subject",
        sender="test@example.com",
        body="This is a test email body",
        user_id=test_user_id,
    )
    await email.insert()

    # Create a task from the email
    task = await map_email_to_task(email)
    await task.insert()

    # Verify task user_id is assigned and matches the email's user_id
    inserted_task = await AssistantTask.get(task.id)
    assert inserted_task.user_id is not None
    assert inserted_task.user_id == test_user_id


@pytest.mark.asyncio
async def test_task_user_id_matches_email_user_id(db_transaction):
    """Test that task user_id always matches its associated email user_id."""
    # Create emails with different user_ids
    user_ids = ["user1", "user2", "user3"]

    for user_id in user_ids:
        email = EmailMessage(
            subject=f"Test for {user_id}",
            sender=f"{user_id}@example.com",
            body=f"Test body for {user_id}",
            user_id=user_id,
        )
        await email.insert()

        # Create task from email
        task = await map_email_to_task(email)
        await task.insert()

        # Verify the task user_id matches the email user_id
        assert task.user_id == user_id


@pytest.mark.asyncio
async def test_direct_task_creation_maintains_user_id_consistency(db_transaction):
    """Test that direct task creation without the mapper maintains user_id consistency."""
    # Create an email
    email = EmailMessage(
        subject="Test Subject",
        sender="test@example.com",
        body="This is a test email body",
        user_id="direct_test_user",
    )
    await email.insert()

    # Create a task directly, setting the user_id to something different
    # The validator should override this with the email's user_id
    task = AssistantTask(
        email=email,
        subject="Direct Task Subject",
        sender="direct@example.com",
        user_id="different_user_id",  # This should be overridden
    )
    await task.insert()

    # Verify the task's user_id matches the email's user_id, not the provided one
    inserted_task = await AssistantTask.get(task.id)
    assert inserted_task.user_id == email.user_id
    assert inserted_task.user_id != "different_user_id"
