# backend/tests/test_routes/test_email.py
import pytest


@pytest.mark.asyncio
async def test_create_email_task(async_client):
    payload = {
        "sender": "alice@example.com",
        "subject": "Test Subject",
        "body": "Test Body",
    }
    response = await async_client.post("/api/v1/email", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "email_id" in data
    assert "task_id" in data
