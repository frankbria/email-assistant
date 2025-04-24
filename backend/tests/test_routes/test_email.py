# backend/tests/test_routes/test_email.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask


def test_create_email_task(client):
    """Test that POST /api/email creates a new email task"""
    payload = {
        "sender": "alice@example.com",
        "subject": "Test Subject",
        "body": "Test Body",
    }
    response = client.post("/api/v1/email", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "email_id" in data
    assert "task_id" in data
