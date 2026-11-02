# backend/tests/test_routes/test_malformed_email_api.py

import pytest
from app.models.assistant_task import AssistantTask
from app.models.email_message import EmailMessage


@pytest.mark.asyncio
async def test_api_missing_subject_and_body(async_client, db_transaction):
    """Test that the API handles requests with missing subject and body."""
    # Define minimal test email data (only sender is required)
    test_email = {
        "sender": "minimal@example.com"
        # Subject and body are intentionally omitted
    }

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Verify response contains email_id and task_id
    assert "email_id" in result
    assert "task_id" in result

    # Retrieve the created task
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)

    # Verify defaults were applied correctly
    assert task.sender == "minimal@example.com"
    assert task.subject == "(No Subject)"
    assert task.summary is not None
    assert isinstance(task.actions, list)
    assert len(task.actions) > 0


@pytest.mark.asyncio
async def test_api_empty_fields(async_client, db_transaction):
    """Test that the API handles requests with empty fields."""
    # Define test email data with empty fields
    test_email = {"sender": "empty_fields@example.com", "subject": "", "body": ""}

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created task
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)

    # Verify defaults were applied correctly
    assert task.sender == "empty_fields@example.com"
    assert task.subject == "(No Subject)"
    assert task.summary == "(No Subject)"


@pytest.mark.asyncio
async def test_api_whitespace_only_fields(async_client, db_transaction):
    """Test that the API handles requests with whitespace-only fields."""
    # Define test email data with whitespace-only fields
    test_email = {
        "sender": "whitespace@example.com",
        "subject": "   \t\n   ",
        "body": "   \t\n   ",
    }

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created task
    task_id = result["task_id"]
    task = await AssistantTask.get(task_id)

    # Verify defaults were applied correctly
    assert task.sender == "whitespace@example.com"
    assert task.subject == "(No Subject)"
    assert task.summary == "(No Subject)"


@pytest.mark.asyncio
async def test_api_special_characters_handling(async_client, db_transaction):
    """Test that the API handles special characters properly."""
    # Define test email with special characters
    test_email = {
        "sender": "special+chars@例子.com",
        "subject": "Tést with 📧 symbols & HTML <tags>",
        "body": "Body with symbols: 💡🔍\nAnd line breaks\nAnd more text",
    }

    # Submit the email via API
    response = await async_client.post("/api/v1/email", json=test_email)
    assert response.status_code == 200
    result = response.json()

    # Retrieve the created email and task
    email_id = result["email_id"]
    task_id = result["task_id"]

    email = await EmailMessage.get(email_id)
    task = await AssistantTask.get(task_id)

    # Verify fields were preserved correctly
    assert email.sender == test_email["sender"]
    assert email.subject == test_email["subject"]
    assert email.body == test_email["body"]

    assert task.sender == test_email["sender"]
    assert task.subject == test_email["subject"]
    assert task.summary is not None


