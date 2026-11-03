# backend/tests/test_routes/test_email_end_to_end.py

import pytest
from beanie import PydanticObjectId

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask


@pytest.mark.asyncio
@pytest.mark.e2e  # Mark this test as an end-to-end test
async def test_email_to_task_end_to_end_flow(async_client, db_transaction):
    """
    End-to-end test that verifies the complete flow:
    1. POST email to API endpoint
    2. Verify email is created in database
    3. Verify task is created from email
    """
    # Step 1: Create a test email
    test_email = {
        "sender": "e2e_test@example.com",
        "subject": "End-to-End Test Email",
        "body": "This is a comprehensive end-to-end test of the email to task flow.",
    }

    # Step 2: Submit the email via API
    post_response = await async_client.post("/api/v1/email", json=test_email)
    assert post_response.status_code == 200
    result = post_response.json()

    # Verify we got both IDs back
    assert "email_id" in result, "Response should include email_id"
    assert "task_id" in result, "Response should include task_id"

    email_id = result["email_id"]
    task_id = result["task_id"]

    # Step 3: Verify the email was saved to database with correct data
    email = await EmailMessage.get(email_id)
    assert email is not None, "Email should be saved in database"
    assert email.sender == test_email["sender"]
    assert email.subject == test_email["subject"]
    assert email.body == test_email["body"]

    # Step 4: Verify the task was created with correct data
    task = await AssistantTask.get(task_id)
    assert task is not None, "Task should be created in database"
    assert task.sender == test_email["sender"]
    assert task.subject == test_email["subject"]

    # Verify task has the email linked
    await task.fetch_link(AssistantTask.email)
    assert task.email.id == PydanticObjectId(email_id), "Task should link to the created email"

    # Verify task has been properly populated
    assert task.summary is not None, "Task should have a summary"
    assert task.context is not None, "Task should have a context"
    assert isinstance(task.actions, list), "Task should have an actions list"
    assert len(task.actions) > 0, "Task should have at least one action"


