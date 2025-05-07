# backend/tests/test_services/test_user_data_isolation.py

import pytest
from beanie import PydanticObjectId

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.config import get_settings


@pytest.mark.asyncio
async def test_email_query_filters_by_user_id(db_transaction):
    """Test that EmailMessage queries only return data for the specified user_id."""
    # Create test emails for different users
    user_ids = ["user1", "user2", "user3"]
    emails_per_user = 3

    for user_id in user_ids:
        for i in range(emails_per_user):
            email = EmailMessage(
                subject=f"Test for {user_id} #{i}",
                sender=f"{user_id}@example.com",
                body=f"Test body for {user_id} #{i}",
                user_id=user_id,
            )
            await email.insert()

    # Verify total number of emails inserted
    total_emails = await EmailMessage.find_all().count()
    assert total_emails == len(user_ids) * emails_per_user

    # Query emails for each user_id and verify only correct emails are returned
    for user_id in user_ids:
        user_emails = await EmailMessage.find({"user_id": user_id}).to_list()
        assert len(user_emails) == emails_per_user

        # Verify each email belongs to the correct user
        for email in user_emails:
            assert email.user_id == user_id
            assert user_id in email.subject  # We included the user_id in the subject
            assert user_id in email.sender  # We included the user_id in the sender


@pytest.mark.asyncio
async def test_task_query_filters_by_user_id(db_transaction):
    """Test that AssistantTask queries only return data for the specified user_id."""
    # Create test tasks for different users
    user_ids = ["user1", "user2", "user3"]
    tasks_per_user = 2

    for user_id in user_ids:
        for i in range(tasks_per_user):
            # Create an email for this task
            email = EmailMessage(
                subject=f"Email for {user_id} #{i}",
                sender=f"{user_id}@example.com",
                body=f"Email body for {user_id} #{i}",
                user_id=user_id,
            )
            await email.insert()

            # Create a task linked to this email
            task = AssistantTask(
                email=email,
                subject=f"Task for {user_id} #{i}",
                sender=f"{user_id}@example.com",
                user_id=user_id,
                actions=["Reply", "Forward"],
            )
            await task.insert()

    # Verify total number of tasks inserted
    total_tasks = await AssistantTask.find_all().count()
    assert total_tasks == len(user_ids) * tasks_per_user

    # Query tasks for each user_id and verify only correct tasks are returned
    for user_id in user_ids:
        user_tasks = await AssistantTask.find({"user_id": user_id}).to_list()
        assert len(user_tasks) == tasks_per_user

        # Verify each task belongs to the correct user
        for task in user_tasks:
            assert task.user_id == user_id
            assert user_id in task.subject  # We included the user_id in the subject
            assert user_id in task.sender  # We included the user_id in the sender
            # Verify the email associated with the task also belongs to the same user
            assert task.email.user_id == user_id


@pytest.mark.asyncio
async def test_api_endpoints_filter_by_user_id(async_client, db_transaction):
    """Test that API endpoints filter data by user_id."""
    # Create test data for different users
    user_ids = ["api_user1", "api_user2"]
    emails_per_user = 2

    # Create emails and tasks for different users
    for user_id in user_ids:
        for i in range(emails_per_user):
            email = EmailMessage(
                subject=f"Test for {user_id} #{i}",
                sender=f"{user_id}@example.com",
                body=f"Test body for {user_id} #{i}",
                user_id=user_id,
                is_spam=(i == 0),  # Mark first email as spam for each user
            )
            await email.insert()

            # Create a task for non-spam emails
            if i > 0:
                task = AssistantTask(
                    email=email,
                    subject=f"Task for {user_id} #{i}",
                    status="pending",
                    user_id=user_id,
                )
                await task.insert()

    # Test tasks endpoint with different user_ids
    for user_id in user_ids:
        # Request tasks for specific user
        response = await async_client.get(f"/api/v1/tasks/?user_id={user_id}")
        assert response.status_code == 200

        # Parse the response data
        tasks = response.json()
        assert len(tasks) == emails_per_user - 1  # One fewer task because of spam email

        # Verify all returned tasks belong to the specified user
        for task in tasks:
            assert task["user_id"] == user_id

    # Test spam endpoint with different user_ids
    for user_id in user_ids:
        # Request spam emails for specific user
        response = await async_client.get(f"/api/v1/email/spam?user_id={user_id}")
        assert response.status_code == 200

        # Parse the response data
        spam_emails = response.json()
        assert len(spam_emails) == 1  # We marked 1 email as spam per user

        # Verify the spam email belongs to the specified user
        assert spam_emails[0]["user_id"] == user_id


@pytest.mark.asyncio
async def test_mixed_user_data_query_isolation(db_transaction):
    """Test that queries don't leak data between users even with complex criteria."""
    # Create emails with similar content but different users
    email1 = EmailMessage(
        subject="Important meeting",
        sender="boss@example.com",
        body="Please attend the meeting tomorrow",
        user_id="user1",
        is_spam=False,
    )
    email2 = EmailMessage(
        subject="Important meeting",
        sender="boss@example.com",
        body="Please attend the meeting tomorrow",
        user_id="user2",
        is_spam=False,
    )
    await email1.insert()
    await email2.insert()

    # Create tasks for these emails
    task1 = AssistantTask(
        email=email1,
        subject="Important meeting",
        sender="boss@example.com",
        user_id="user1",
        status="pending",
        context="Work",
    )
    task2 = AssistantTask(
        email=email2,
        subject="Important meeting",
        sender="boss@example.com",
        user_id="user2",
        status="pending",
        context="Work",
    )
    await task1.insert()
    await task2.insert()

    # Test complex query for first user that could potentially leak data
    user1_tasks = await AssistantTask.find(
        {"user_id": "user1", "subject": "Important meeting", "context": "Work"}
    ).to_list()

    # Should only return task for user1
    assert len(user1_tasks) == 1
    assert user1_tasks[0].user_id == "user1"

    # Test complex query for second user
    user2_tasks = await AssistantTask.find(
        {"user_id": "user2", "subject": "Important meeting", "context": "Work"}
    ).to_list()

    # Should only return task for user2
    assert len(user2_tasks) == 1
    assert user2_tasks[0].user_id == "user2"

    # Verify different task IDs (they should be different objects)
    assert user1_tasks[0].id != user2_tasks[0].id
