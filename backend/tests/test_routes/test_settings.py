# backend/tests/test_routes/test_settings.py
import pytest
from fastapi.testclient import TestClient
from app.models.user_settings import UserSettings
from app.api.routers.settings import DEFAULT_USER_ID


def test_get_settings_for_new_user(client):
    """
    Test that GET /api/v1/settings/email returns default settings for a new user
    that doesn't have settings yet.
    """
    # Make sure user doesn't exist in test DB
    user_id = "new_test_user"

    # Override default user_id for this test
    url = f"/api/v1/settings/email?user_id={user_id}"

    # Fetch settings
    response = client.get(url)

    # Check status code and response structure
    assert response.status_code == 200
    data = response.json()

    # Verify default settings are returned
    assert data["user_id"] == user_id
    assert data["enable_spam_filtering"] is True  # Default value is True
    assert data["enable_auto_categorization"] is True  # Default value is True
    assert data["skip_low_priority_emails"] is False  # Default value is False


@pytest.mark.skip(reason="Issues with async fixture and event loop")
@pytest.mark.asyncio
async def test_get_settings_for_existing_user(async_client):
    """
    Test that GET /api/v1/settings/email returns the correct settings for an existing user.
    """
    user_id = "default_user"

    # Prepopulate DB with known user settings using PATCH
    reset_payload = {
        "enable_spam_filtering": False,
        "enable_auto_categorization": False,
        "skip_low_priority_emails": True,
    }

    # Set initial state
    patch_response = await async_client.patch(
        f"/api/v1/settings/email?user_id={user_id}",
        json=reset_payload,
    )

    print("PATCH response: ", patch_response.status_code, patch_response.text)

    assert patch_response.status_code in (200, 201)

    # Fetch current settings
    response = await async_client.get(f"/api/v1/settings/email?user_id={user_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["user_id"] == user_id
    assert data["enable_spam_filtering"] is False
    assert data["enable_auto_categorization"] is False
    assert data["skip_low_priority_emails"] is True


def test_update_settings(client):
    """
    Test that PATCH /api/v1/settings/email correctly updates settings.
    """
    # Prepare update payload
    update_payload = {
        "enable_spam_filtering": False,
        "enable_auto_categorization": True,
        "skip_low_priority_emails": True,
    }

    # Send PATCH request
    response = client.patch("/api/v1/settings/email", json=update_payload)

    # Check status code and response structure
    assert response.status_code == 200
    data = response.json()

    # Verify settings were updated
    assert data["user_id"] == DEFAULT_USER_ID
    assert data["enable_spam_filtering"] is False
    assert data["enable_auto_categorization"] is True
    assert data["skip_low_priority_emails"] is True

    # Fetch settings to confirm persistence
    get_response = client.get("/api/v1/settings/email")
    assert get_response.status_code == 200
    get_data = get_response.json()

    # Verify settings match what we updated
    assert get_data["enable_spam_filtering"] is False
    assert get_data["enable_auto_categorization"] is True
    assert get_data["skip_low_priority_emails"] is True


def test_partial_update_settings(client):
    """
    Test that PATCH /api/v1/settings/email correctly updates only the specified fields.
    """
    # First, reset settings to known state
    full_payload = {
        "enable_spam_filtering": True,
        "enable_auto_categorization": True,
        "skip_low_priority_emails": False,
    }
    reset_resp = client.patch("/api/v1/settings/email", json=full_payload)
    assert reset_resp.status_code == 200

    # Now do a partial update
    partial_payload = {
        "enable_spam_filtering": False,
    }

    response = client.patch("/api/v1/settings/email", json=partial_payload)

    # Check status code and response structure
    assert response.status_code == 200
    data = response.json()

    # Verify only specified setting was updated, others unchanged
    assert data["enable_spam_filtering"] is False  # Changed
    assert data["enable_auto_categorization"] is True  # Unchanged
    assert data["skip_low_priority_emails"] is False  # Unchanged


def test_empty_update_payload(client):
    """
    Test that PATCH /api/v1/settings/email with empty payload returns 400 Bad Request.
    """
    # Send empty payload
    response = client.patch("/api/v1/settings/email", json={})

    # Should return 400 Bad Request
    assert response.status_code == 400
    assert "No fields provided for update" in response.json()["detail"]


def test_invalid_update_payload(client):
    """
    Test that PATCH /api/v1/settings/email with invalid payload returns 422 Validation Error.
    """
    # Send invalid payload (wrong type)
    response = client.patch(
        "/api/v1/settings/email", json={"enable_spam_filtering": "not-a-boolean"}
    )

    # Should return 422 Unprocessable Entity
    assert response.status_code == 422

    # The detail field is a list of validation errors
    detail = response.json()["detail"]
    assert isinstance(detail, list)

    # Check that at least one error contains validation-related text
    error_found = False
    for error in detail:
        error_str = str(error).lower()
        if any(term in error_str for term in ["type", "bool", "validation"]):
            error_found = True
            break

    assert error_found, "Expected to find a type/validation error about boolean values"
