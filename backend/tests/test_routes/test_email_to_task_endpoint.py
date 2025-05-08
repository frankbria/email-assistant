# backend/tests/test_routes/test_email_to_task_endpoint.py

import pytest
from httpx import AsyncClient
from fastapi import FastAPI

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask


@pytest.mark.asyncio
async def test_email_submission_creates_task(async_client, db_transaction):
    """Test that submitting an email via the API endpoint results in a properly created task."""
    # Define test email data
    test_email = {
        "sender": "api_test@example.com",
        "subject": "Test Email Submission",
        "body": "This is a test email submitted through the API endpoint.",
    }

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Verify response contains email_id and task_id
    assert "email_id" in result
    assert "task_id" in result

    # Retrieve the created email and task from database
    email_id = result["email_id"]
    task_id = result["task_id"]

    email = await EmailMessage.get(email_id)
    task = await AssistantTask.get(task_id)

    # Verify email was stored correctly
    assert email.sender == test_email["sender"]
    assert email.subject == test_email["subject"]
    assert email.body == test_email["body"]

    # Verify task was created with correct fields
    assert task.sender == test_email["sender"]
    assert task.subject == test_email["subject"]

    # Instead of directly comparing IDs, fetch the linked email and then compare
    await task.fetch_link(AssistantTask.email)
    assert task.email.id == email.id
    assert task.summary is not None
    assert task.context is not None
    assert isinstance(task.actions, list)
    assert len(task.actions) > 0


@pytest.mark.asyncio
async def test_email_with_custom_actions(async_client, db_transaction):
    """Test that submitting an email with custom actions creates a task with those actions."""
    # Define test email data with custom actions
    test_email = {
        "sender": "api_test@example.com",
        "subject": "Test Email with Custom Actions",
        "body": "This is a test email submitted with custom actions.",
        "actions": ["Approve", "Reject", "Request Changes"],
    }

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created task from database
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)

    # Verify custom actions were used
    assert task.actions == test_email["actions"]


@pytest.mark.asyncio
async def test_user_specific_email_submission(async_client, db_transaction):
    """Test that submitting an email with a user_id parameter assigns the correct user_id."""
    # Define test email data
    test_email = {
        "sender": "api_test@example.com",
        "subject": "Test Email with User ID",
        "body": "This is a test email submitted with a specific user ID.",
    }

    # Use a specific test user ID
    test_user_id = "user_specific_test"

    # Submit the email via API with user_id parameter
    response = await async_client.post(
        f"/api/v1/email?user_id={test_user_id}", json=test_email
    )
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created email and task from database
    email_id = result["email_id"]
    task_id = result["task_id"]

    email = await EmailMessage.get(email_id)
    task = await AssistantTask.get(task_id)

    # Verify user_id was assigned correctly to both email and task
    assert email.user_id == test_user_id
    assert task.user_id == test_user_id


@pytest.mark.asyncio
async def test_webhook_email_submission_creates_task(async_client, db_transaction):
    """Test that submitting an email via the webhook endpoint results in a properly created task."""
    # First, we need to set up the webhook security configuration
    from app.models.webhook_security import WebhookSecurity

    # Create webhook security configuration
    test_api_key = "test_webhook_key_12345"
    test_client_ip = "127.0.0.1"  # Test client IP

    webhook_config = WebhookSecurity(
        api_key=test_api_key, allowed_ips=[test_client_ip], active=True
    )
    await webhook_config.insert()

    # Define test email data
    test_email = {
        "sender": "webhook_test@example.com",
        "subject": "Test Webhook Email Submission",
        "body": "This is a test email submitted through the webhook endpoint.",
    }

    # Set up webhook headers
    headers = {"x-api-key": test_api_key, "x-forwarded-for": test_client_ip}

    # Submit the email via webhook API
    response = await async_client.post(
        "/api/v1/email/incoming", json=test_email, headers=headers
    )
    assert response.status_code == 200
    result = response.json()

    # Verify response contains email_id and task_id
    assert "email_id" in result
    assert "task_id" in result

    # Retrieve the created email and task from database
    email_id = result["email_id"]
    task_id = result["task_id"]

    email = await EmailMessage.get(email_id)
    task = await AssistantTask.get(task_id)

    # Verify email was stored correctly
    assert email.sender == test_email["sender"]
    assert email.subject == test_email["subject"]
    assert email.body == test_email["body"]

    # Verify task was created with correct fields
    assert task.sender == test_email["sender"]
    assert task.subject == test_email["subject"]

    # Instead of directly comparing IDs, fetch the linked email and then compare
    await task.fetch_link(AssistantTask.email)
    assert task.email.id == email.id
    assert task.summary is not None
    assert isinstance(task.actions, list)
    assert len(task.actions) > 0


@pytest.mark.asyncio
async def test_malformed_email_handled_gracefully(async_client, db_transaction):
    """Test that a malformed or incomplete email is handled gracefully with defaults."""
    # Submit a minimal/malformed email
    test_email = {
        # Missing subject and body
        "sender": "minimal@example.com"
    }

    # Submit via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created task
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)

    # Verify default values were used appropriately
    assert task.subject == "(No Subject)"  # Default subject
    assert task.summary is not None  # Summary still generated
    assert isinstance(task.actions, list)  # Actions still provided
    assert len(task.actions) > 0
