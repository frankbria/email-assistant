# backend/tests/test_scripts/test_migrate_user_id.py

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the scripts directory to the path so we can import the migration script
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from scripts.migrate_user_id import (
    migrate_email_messages,
    migrate_assistant_tasks,
    validate_migration,
)
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask


@pytest.mark.asyncio
async def test_migrate_email_messages(db):
    # Create test emails without user_id
    test_emails = [
        EmailMessage(subject="Test 1", sender="test@example.com", body="test body 1"),
        EmailMessage(subject="Test 2", sender="test@example.com", body="test body 2"),
        EmailMessage(subject="Test 3", sender="test@example.com", body="test body 3"),
    ]

    # Insert them directly to bypass validation
    await EmailMessage.insert_many(test_emails)

    # Verify they don't have user_id
    emails_without_user_id = await EmailMessage.find(
        {"user_id": {"$exists": False}}
    ).count()
    assert emails_without_user_id == 3

    # Run the migration
    result = await migrate_email_messages("test_user")

    # Check the migration stats
    assert result["total"] == 3
    assert result["updated"] == 3

    # Verify all emails now have user_id
    emails_without_user_id = await EmailMessage.find(
        {"user_id": {"$exists": False}}
    ).count()
    assert emails_without_user_id == 0

    # Verify the user_id is correct
    all_emails = await EmailMessage.find_all().to_list()
    for email in all_emails:
        assert email.user_id == "test_user"


@pytest.mark.asyncio
async def test_migrate_assistant_tasks(db):
    # Create an email with user_id for the task
    email = EmailMessage(
        subject="Test Email",
        sender="test@example.com",
        body="test body",
        user_id="test_user",
    )
    await email.insert()

    # Create test tasks without user_id (directly to bypass validation)
    test_tasks = [
        {"email": email, "status": "pending"},
        {"email": email, "status": "in_progress"},
        {"email": email, "status": "done"},
    ]

    tasks = [AssistantTask(**task) for task in test_tasks]
    for task in tasks:
        # We're using save() directly to bypass validators
        await task.save()

    # Verify they don't have user_id
    tasks_without_user_id = await AssistantTask.find(
        {"user_id": {"$exists": False}}
    ).count()
    assert tasks_without_user_id == 3

    # Run the migration
    result = await migrate_assistant_tasks("test_user")

    # Check the migration stats
    assert result["total"] == 3
    assert result["updated"] == 3

    # Verify all tasks now have user_id
    tasks_without_user_id = await AssistantTask.find(
        {"user_id": {"$exists": False}}
    ).count()
    assert tasks_without_user_id == 0

    # Verify the user_id is correct
    all_tasks = await AssistantTask.find_all().to_list()
    for task in all_tasks:
        assert task.user_id == "test_user"


@pytest.mark.asyncio
async def test_validate_migration(db):
    # Create one email and task without user_id
    email = EmailMessage(subject="Test", sender="test@example.com", body="test body")
    await email.save(validate=False)  # Skip validation to omit user_id

    task = AssistantTask(email=email, status="pending")
    await task.save(validate=False)  # Skip validation to omit user_id

    # Run validation - should find one of each missing user_id
    result = await validate_migration()
    assert result["emails_missing_user_id"] == 1
    assert result["tasks_missing_user_id"] == 1

    # Add user_id to both
    email.user_id = "test_user"
    await email.save()

    task.user_id = "test_user"
    await task.save()

    # Validate again - should find none missing
    result = await validate_migration()
    assert result["emails_missing_user_id"] == 0
    assert result["tasks_missing_user_id"] == 0
