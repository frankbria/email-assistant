# backend/tests/test_routes/test_tasks.py
import pytest
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask


def test_get_tasks(client):
    """Test that GET /api/tasks returns a list of tasks"""
    # First, create a task via the API so that we know at least one exists
    payload = {
        "sender": "alice@example.com",
        "subject": "Task Subject",
        "body": "Task Body",
    }
    post_resp = client.post("/api/v1/email", json=payload)
    assert post_resp.status_code == 200, "Precondition: email creation should succeed"

    # Now retrieve tasks
    response = client.get("/api/v1/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0, "There should be at least one task returned"

    task = data[0]
    assert "email" in task
    assert "subject" in task["email"]
    assert "sender" in task["email"]
    assert "body" in task["email"]
    assert "context" in task
    assert "summary" in task
    assert "suggested_actions" in task
    assert "status" in task
