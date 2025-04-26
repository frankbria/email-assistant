# backend/tests/test_routes/test_email.py
import pytest
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
    # Fetch all tasks and find the newly created one by its email subject
    tasks_resp = client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    # locate the task whose embedded email.subject matches our payload
    created = next(
        (t for t in tasks if t.get("email", {}).get("subject") == payload["subject"]),
        None,
    )
    assert created is not None, f"Task with subject '{payload['subject']}' not found"
    # Ensure the task context field is present
    assert "context" in created


def test_email_task_context_integration(client):
    """
    When I POST an email containing scheduling keywords,
    the saved task's context should be 'scheduling'.
    """
    payload = {
        "sender": "bob@example.com",
        "subject": "Please schedule a call",
        "body": "Are you free to schedule a 1:1 next Tuesday?",
    }
    # Create the task
    resp = client.post("/api/v1/email", json=payload)
    assert resp.status_code == 200

    # Fetch tasks and locate ours by subject
    tasks = client.get("/api/v1/tasks/").json()
    task = next(t for t in tasks if t["email"]["subject"] == payload["subject"])

    # It should have been classified as 'scheduling'
    assert task["context"] == "scheduling"
