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


