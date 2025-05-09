# backend/tests/test_routes/test_email.py
import pytest
from app.strategies.action_registry import ActionRegistry
from app.strategies.default import DefaultEmailStrategy


def test_create_email_task(client, monkeypatch):
    """Test that POST /api/v1/email creates a new email task"""
    ActionRegistry._strategies.clear()
    ActionRegistry.register("default", DefaultEmailStrategy)
    monkeypatch.setattr(
        ActionRegistry, "get_default_strategies", lambda: [DefaultEmailStrategy]
    )
    monkeypatch.setattr(
        "os.environ",
        {
            "USE_AI_CONTEXT": "false",
            "USE_AI_SUMMARY": "false",
        },
    )
    payload = {
        "sender": "alice@example.com",
        "subject": "Test",
        "body": "Test Email.",
    }
    response = client.post("/api/v1/email", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "email_id" in data
    assert "task_id" in data
    print(f"🔄 Created email: {data}")

    # Fetch all tasks and verify the created one
    tasks_resp = client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    print(f"🔄 Fetched tasks: {tasks}")

    created = next(
        (t for t in tasks if t.get("email", {}).get("subject") == payload["subject"]),
        None,
    )
    assert created is not None, f"Task with subject '{payload['subject']}' not found"
    assert "context" in created

    # Verify actions list
    assert "actions" in created
    assert isinstance(created["actions"], list)
    assert 2 <= len(created["actions"]) <= 3, "Should have 2-3 suggested actions"
    # Common actions that should typically be available
    action_labels = set(created["actions"])
    print(f"🔄 Action labels: {action_labels}")
    assert any(
        label in action_labels for label in ["Reply", "Forward", "Archive"]
    ), "Should include basic email actions"


def test_email_task_context_integration(client, monkeypatch):
    """
    When I POST an email containing scheduling keywords,
    the saved task's context should be 'scheduling'.
    """
    payload = {
        "sender": "bob@example.com",
        "subject": "Please schedule a call",
        "body": "Are you free to schedule a 1:1 next Tuesday?",
    }

    # ❗ Correct: async fake
    async def fake_classify(subject, body):
        return "scheduling"

    monkeypatch.setattr(
        "app.api.routers.email.context_classifier.classify_context",
        fake_classify,
    )

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )

    resp = client.post("/api/v1/email", json=payload)
    assert resp.status_code == 200

    tasks_resp = client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()

    task = next(
        (t for t in tasks if t["email"]["subject"] == payload["subject"]),
        None,
    )
    assert task is not None, "Created task not found"
    assert task["context"] == "scheduling"

    # Verify context-specific actions
    assert "actions" in task
    assert isinstance(task["actions"], list)
    assert 2 <= len(task["actions"]) <= 3, "Should have 2-3 suggested actions"
    action_labels = set(task["actions"])
    assert any(
        "Schedule" in label or "Reply" in label for label in action_labels
    ), "Should include scheduling-related actions"


def test_email_task_actions_fallback(client, monkeypatch):
    """Test that tasks always get actions even if suggestion fails"""
    payload = {
        "sender": "charlie@example.com",
        "subject": "Test fallback",
        "body": "Testing action fallback",
    }

    # Mock action suggestion to fail
    async def mock_suggest_actions(*args, **kwargs):
        raise Exception("Action suggestion failed")

    monkeypatch.setattr(
        "app.services.email_task_mapper.suggest_actions",
        mock_suggest_actions,
    )

    resp = client.post("/api/v1/email", json=payload)
    assert resp.status_code == 200

    tasks_resp = client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()

    task = next(
        (t for t in tasks if t["email"]["subject"] == payload["subject"]),
        None,
    )
    assert task is not None, "Created task not found"

    # Should still have default actions
    assert "actions" in task
    assert isinstance(task["actions"], list)
    assert len(task["actions"]) >= 2, "Should have at least 2 default actions"
    assert "Reply" in task["actions"], "Should include Reply action"


# @pytest.mark.skip
@pytest.mark.asyncio
async def test_incoming_webhook_duplicate_detection(async_client, set_webhook_security):
    """Ensure duplicate incoming emails are rejected with 409 and do not create new tasks."""
    payload = {"sender": "dup@example.com", "subject": "Dup", "body": "Dup Body"}
    headers = {"x-api-key": "validkey"}

    # First incoming webhook call should succeed
    resp1 = await async_client.post(
        "/api/v1/email/incoming", json=payload, headers=headers
    )
    assert resp1.status_code == 200
    # Capture task count after first call
    tasks_resp = await async_client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    initial_tasks = tasks_resp.json()
    count_after_first = len(initial_tasks)
    # Second call with same payload should be conflict
    resp2 = await async_client.post(
        "/api/v1/email/incoming", json=payload, headers=headers
    )
    assert resp2.status_code == 409
    assert resp2.json().get("detail") == "Duplicate email."
    # Ensure no new task was created
    tasks_resp2 = await async_client.get("/api/v1/tasks/")
    assert len(tasks_resp2.json()) == count_after_first


@pytest.mark.asyncio
async def test_incoming_forwarded_email(async_client, set_webhook_security):
    """Test that forwarded emails are processed correctly."""
    payload = {
        "sender": "alice@example.com",
        "subject": "Fwd: Important Meeting",
        "body": "------------Forwarded Message--------------------\nFrom: john@forwarded.com\nTo: alice@example.com\nSubject: Important Meeting\n\nFwd: Please see the attached agenda for the meeting.",
    }

    headers = {"x-api-key": "validkey", "x-forwarded-for": "127.0.0.1"}
    async_client.headers.update(headers)

    resp = await async_client.post("/api/v1/email/incoming", json=payload)
    assert resp.status_code == 200

    tasks_resp = await async_client.get("/api/v1/tasks/")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()

    task = next(
        (t for t in tasks if t["email"]["subject"] == "Important Meeting"),
        None,
    )
    assert task is not None, "Created task not found"
    assert task["email"]["sender"] == "john@forwarded.com"
    assert task["email"]["subject"] == "Important Meeting"

    # Verify context-specific actions
    assert "actions" in task
    assert isinstance(task["actions"], list)
    assert 2 <= len(task["actions"]) <= 3, "Should have 2-3 suggested actions"
    action_labels = set(task["actions"])
