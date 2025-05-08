# backend/tests/test_routes/test_email_end_to_end.py

import pytest
from httpx import AsyncClient
from beanie import PydanticObjectId
import json

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
    4. Fetch tasks from API and verify the new task is included
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

    # Step 5: Fetch all tasks and verify our new task is included
    list_response = await async_client.get("/api/v1/tasks/")
    assert list_response.status_code == 200, "Tasks endpoint should be accessible"
    
    tasks_list = list_response.json()
    
    # Debug: Print the structure of the first task in the list
    if tasks_list:
        print(f"DEBUG - Task structure: {json.dumps(tasks_list[0], indent=2)}")
        print(f"DEBUG - Task ID we're looking for: {task_id}")
        print(f"DEBUG - Keys available in task: {list(tasks_list[0].keys())}")
    
    # Find our task in the list based on the ID field
    # We'll try different possible field names for the ID
    found_task = None
    for t in tasks_list:
        # Try different possible field names for the task ID
        if '_id' in t and t['_id'] == task_id:
            found_task = t
            break
        elif 'id' in t and t['id'] == task_id:
            found_task = t
            break
        elif 'task_id' in t and t['task_id'] == task_id:
            found_task = t
            break
    
    assert found_task is not None, "Created task should be included in the list of tasks"
    assert found_task["sender"] == test_email["sender"], "Task data should match original email"
    assert found_task["subject"] == test_email["subject"], "Task data should match original email"
    assert "email" in found_task, "Task should include email reference"
    assert found_task["email"]["id"] == email_id or found_task["email"]["_id"] == email_id, "Task should reference the original email"


@pytest.mark.asyncio
@pytest.mark.e2e  # Mark this test as an end-to-end test
async def test_webhook_email_to_task_end_to_end_flow(async_client, set_webhook_security, db_transaction):
    """
    End-to-end test that verifies the complete flow using the webhook endpoint:
    1. POST email to webhook endpoint
    2. Verify email is created in database
    3. Verify task is created from email
    4. Fetch tasks from API and verify the new task is included
    """
    # Step 1: Create a test email for webhook
    test_email = {
        "sender": "webhook_e2e@example.com",
        "subject": "Webhook End-to-End Test Email",
        "body": "This is a comprehensive end-to-end test of the webhook to task flow.",
    }

    # Setup webhook headers
    headers = {"x-api-key": "validkey", "x-forwarded-for": "127.0.0.1"}

    # Step 2: Submit the email via webhook endpoint
    post_response = await async_client.post(
        "/api/v1/email/incoming", json=test_email, headers=headers
    )
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

    # Step 5: Fetch all tasks and verify our new task is included
    list_response = await async_client.get("/api/v1/tasks/")
    assert list_response.status_code == 200, "Tasks endpoint should be accessible"
    
    tasks_list = list_response.json()
    
    # Debug: Print the structure of the first task in the list
    if tasks_list:
        print(f"DEBUG - Task structure: {json.dumps(tasks_list[0], indent=2)}")
        print(f"DEBUG - Task ID we're looking for: {task_id}")
        print(f"DEBUG - Keys available in task: {list(tasks_list[0].keys())}")
    
    # Find our task in the list based on the ID field
    # We'll try different possible field names for the ID
    found_task = None
    for t in tasks_list:
        # Try different possible field names for the task ID
        if '_id' in t and t['_id'] == task_id:
            found_task = t
            break
        elif 'id' in t and t['id'] == task_id:
            found_task = t
            break
        elif 'task_id' in t and t['task_id'] == task_id:
            found_task = t
            break
    
    assert found_task is not None, "Created task should be included in the list of tasks"
    assert found_task["sender"] == test_email["sender"], "Task data should match original email"
    assert found_task["subject"] == test_email["subject"], "Task data should match original email"
    assert "email" in found_task, "Task should include email reference"
    assert found_task["email"]["id"] == email_id or found_task["email"]["_id"] == email_id, "Task should reference the original email"
