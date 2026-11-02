# backend/tests/test_routes/test_email_user_id.py

import pytest

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from tests.utils.auth import OWNER_ID, bearer_headers


@pytest.mark.asyncio
async def test_email_creation_endpoint_sets_user_id(async_client, db_transaction):
    """Test that POST /api/v1/email assigns correct user_id based on the request."""
    # Define test data
    test_email = {
        "sender": "api_test@example.com",
        "subject": "Test API Email Creation",
        "body": "This is a test email created via the API endpoint",
    }

    # Signed in as the default test owner
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Get the created email from the database
    email_id = result["email_id"]
    email = await EmailMessage.get(email_id)

    # The owner comes from the token
    assert email.user_id == OWNER_ID

    # Signed in as another user
    test_user_id = "api_test_user"
    response = await async_client.post(
        "/api/v1/email", json=test_email, headers=bearer_headers(test_user_id)
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


