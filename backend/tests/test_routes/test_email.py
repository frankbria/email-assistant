# backend/tests/test_routes/test_email.py
import pytest
from app.strategies.action_registry import ActionRegistry
from app.strategies.default import DefaultEmailStrategy


def test_create_email_task(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that POST /api/v1/email creates a new email task"""
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


def test_email_task_context_integration(
    client,
    mock_action_registry_scenario,
    mock_settings_scenario,
    mock_context_classifier_scenario,
):
    """
    When I POST an email containing scheduling keywords,
    the saved task's context should be 'scheduling'.
    """
    payload = {
        "sender": "bob@example.com",
        "subject": "Please schedule a call",
        "body": "Are you free to schedule a 1:1 next Tuesday?",
    }
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


def test_email_task_actions_fallback(
    client,
    mock_action_registry_scenario,
    mock_settings_scenario,
    mock_openai_failure_scenario,
):
    """Test that tasks always get actions even if suggestion fails"""
    payload = {
        "sender": "charlie@example.com",
        "subject": "Test fallback",
        "body": "Testing action fallback",
    }
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


# ---
# NEW SCENARIO-BASED TEST STUBS
# ---


def test_email_task_ai_success(
    client, mock_openai_success_scenario, mock_settings_scenario
):
    """Test that AI-generated actions are returned when AI is enabled."""
    pass


def test_email_task_ai_failure_fallback(
    client, mock_openai_failure_scenario, mock_settings_scenario
):
    """Test that fallback to rule-based actions works when AI fails."""
    pass


def test_email_task_multiple_strategies(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that multiple strategies for a context merge their actions correctly."""
    pass


def test_email_task_custom_actions(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that custom actions in the payload override the defaults."""
    pass


def test_email_task_missing_fields(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that missing sender/subject/body are handled gracefully."""
    pass


def test_email_task_malformed_payload(client):
    """Test that malformed JSON or wrong types are handled with a 400 error."""
    pass


def test_email_task_duplicate_emails(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test submitting the same email twice (duplicate handling)."""
    pass


def test_email_task_long_body_subject(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that long body/subject fields are truncated or summarized as expected."""
    pass


def test_email_task_retrieve_all(client):
    """Test that /api/v1/tasks/ returns all created tasks."""
    pass


def test_email_task_retrieve_by_id(client):
    """Test that getting a task by ID returns the correct task or 404 if not found."""
    pass


def test_email_task_data_integrity(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that all expected fields are present and correct in the returned task."""
    pass


def test_email_task_permissions(client):
    """Test that unauthorized or forbidden access is handled correctly (if applicable)."""
    pass


def test_email_task_forwarded_email_parsing(
    client, mock_action_registry_scenario, mock_settings_scenario
):
    """Test that forwarded email headers are parsed for original sender/subject."""
    pass


def test_email_task_bulk_creation(client):
    """Test submitting multiple emails in one request (if supported)."""
    pass


def test_email_task_rate_limiting(client):
    """Test that API rate limits are enforced (if applicable)."""
    pass


def test_email_task_db_error_handling(client):
    """Test that database errors are handled gracefully and return 500 or appropriate error."""
    pass
