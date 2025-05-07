# backend/tests/test_routes/test_email_user_id.py

import pytest
import json
from httpx import AsyncClient
from fastapi import FastAPI

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.config import get_settings


@pytest.mark.asyncio
async def test_email_creation_endpoint_sets_user_id(async_client, db_transaction):
    """Test that POST /api/v1/email assigns correct user_id based on the request."""
    # Define test data
    test_email = {
        "sender": "api_test@example.com",
        "subject": "Test API Email Creation",
        "body": "This is a test email created via the API endpoint",
    }

    # Test with no user_id in query params (should use default)
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Get the created email from the database
    email_id = result["email_id"]
    email = await EmailMessage.get(email_id)

    # Verify default user_id is assigned
    assert email.user_id == get_settings().DEFAULT_USER_ID

    # Test with specific user_id in query params
    test_user_id = "api_test_user"
    response = await async_client.post(
        f"/api/v1/email?user_id={test_user_id}", json=test_email
    )
    assert response.status_code == 200
    result = response.json()

    # Get the created email from the database
    email_id = result["email_id"]
    email = await EmailMessage.get(email_id)

    # Verify specified user_id is assigned
    assert email.user_id == test_user_id

    # Verify the associated task also has the correct user_id
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)
    assert task.user_id == test_user_id


@pytest.mark.asyncio
async def test_incoming_webhook_assigns_user_id(async_client, db_transaction, faker):
    """Test that POST /api/v1/email/incoming assigns correct user_id based on the request."""
    # Create valid webhook security config for testing
    from app.models.webhook_security import WebhookSecurity

    test_api_key = "test_webhook_key_12345"
    test_client_ip = "127.0.0.1"  # This is what the test client will appear as

    # Create or update webhook security config
    webhook_config = await WebhookSecurity.find_one(WebhookSecurity.active == True)
    if webhook_config:
        webhook_config.api_key = test_api_key
        webhook_config.allowed_ips = [test_client_ip]
        await webhook_config.save()
    else:
        webhook_config = WebhookSecurity(
            api_key=test_api_key, allowed_ips=[test_client_ip], active=True
        )
        await webhook_config.insert()

    # Define test data
    test_email = {
        "sender": "webhook_test@example.com",
        "subject": "Test Webhook Email Creation",
        "body": "This is a test email created via the webhook endpoint",
    }

    # Prepare headers
    headers = {
        "x-api-key": test_api_key,
        "x-forwarded-for": test_client_ip,  # Simulate the client IP
    }

    # Test with no user_id in query params (should use default)
    response = await async_client.post(
        "/api/v1/email/incoming", json=test_email, headers=headers
    )

    # Check if this is a duplicate email error (409)
    if response.status_code == 409:
        # This is fine, just means we've run this test before
        # Let's modify the email slightly to make it unique
        test_email["subject"] = (
            f"Test Webhook Email Creation {faker.pystr(min_chars=5, max_chars=5)}"
        )
        response = await async_client.post(
            "/api/v1/email/incoming", json=test_email, headers=headers
        )

    assert response.status_code == 200
    result = response.json()

    # Get the created email from the database
    email_id = result["email_id"]
    email = await EmailMessage.get(email_id)

    # Verify default user_id is assigned
    assert email.user_id == get_settings().DEFAULT_USER_ID

    # Test with specific user_id in query params
    test_user_id = "webhook_test_user"
    test_email["subject"] = (
        f"Test Webhook Email Creation {faker.pystr(min_chars=5, max_chars=5)}"
    )

    response = await async_client.post(
        f"/api/v1/email/incoming?user_id={test_user_id}",
        json=test_email,
        headers=headers,
    )
    assert response.status_code == 200
    result = response.json()

    # Get the created email from the database
    email_id = result["email_id"]
    email = await EmailMessage.get(email_id)

    # Verify specified user_id is assigned
    assert email.user_id == test_user_id

    # Verify the associated task also has the correct user_id
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)
    assert task.user_id == test_user_id
