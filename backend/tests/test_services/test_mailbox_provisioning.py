# backend/tests/test_services/test_mailbox_provisioning.py
import pytest
from unittest.mock import patch, MagicMock
import sys
from importlib import import_module
from app.models.user_settings import UserSettings

# Create mock module
mock_config = MagicMock()
mock_config.mailbox_api_key = "mock-api-key"

# Mock the settings before importing
sys.modules["app.config"] = MagicMock()
sys.modules["app.config"].get_settings = MagicMock(return_value=mock_config)

# Now we can import the module
from app.services.mailbox_provisioning import provision_mailbox

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_mailslurp_inbox():
    """Fixture to mock the MailSlurp inbox creation response"""
    inbox_mock = MagicMock()
    inbox_mock.userId = "mock-mailbox-id-12345"
    inbox_mock.name = "Mailbox Assistant for test-user-123"
    inbox_mock.emailAddress = "test-user-123@example.com"
    return inbox_mock


@patch("app.services.mailbox_provisioning.mailslurp_client")
@patch("app.services.mailbox_provisioning.get_settings")
async def test_provision_mailbox_creates_unique_addresses(
    mock_settings, mock_mailslurp, mock_mailslurp_inbox
):
    """Test that mailbox provisioning creates unique addresses for different users"""
    # Import here to avoid the initial import error
    from app.services.mailbox_provisioning import provision_mailbox

    # Configure mocks
    settings_instance = MagicMock()
    settings_instance.mailbox_api_key = "mock-api-key"
    mock_settings.return_value = settings_instance

    # Set up the API chain
    mock_config = MagicMock()
    mock_api_client = MagicMock()
    mock_inbox_controller = MagicMock()

    # Configure mock inbox responses for two different users
    inbox1 = MagicMock()
    inbox1.userId = "inbox-id-1"
    inbox1.name = "Inbox for user1"
    inbox1.emailAddress = "user1@example.com"

    inbox2 = MagicMock()
    inbox2.userId = "inbox-id-2"
    inbox2.name = "Inbox for user2"
    inbox2.emailAddress = "user2@example.com"

    # Set up side effects to return different inboxes for different calls
    mock_inbox_controller.create_inbox.side_effect = [inbox1, inbox2]

    # Mock the appropriate methods in the chain
    mock_mailslurp.Configuration.return_value = mock_config
    mock_mailslurp.ApiClient.return_value.__enter__.return_value = mock_api_client
    mock_mailslurp.InboxControllerApi.return_value = mock_inbox_controller

    # Act - provision mailboxes for two different users
    result1 = provision_mailbox("user1")
    result2 = provision_mailbox("user2")

    # Assert - verify uniqueness
    assert result1["email_address"] != result2["email_address"]
    assert result1["mailbox_id"] != result2["mailbox_id"]

    # Assert - verify format and correct naming
    assert "user1" in mock_inbox_controller.create_inbox.call_args_list[0][1]["name"]
    assert "user2" in mock_inbox_controller.create_inbox.call_args_list[1][1]["name"]

    # Assert - proper API key configuration
    # assert mock_config.api_key == {"x-api-key": "mock-api-key"}


@patch("app.services.mailbox_provisioning.mailslurp_client")
@patch("app.services.mailbox_provisioning.get_settings")
async def test_mailbox_proper_configuration(mock_settings, mock_mailslurp):
    """Test that mailbox is configured correctly with proper parameters"""
    # Import here to avoid the initial import error
    from app.services.mailbox_provisioning import provision_mailbox

    # Configure mocks
    settings_instance = MagicMock()
    settings_instance.mailbox_api_key = "mock-api-key"
    mock_settings.return_value = settings_instance

    # Set up the API chain
    mock_config = MagicMock()
    mock_api_client = MagicMock()
    mock_inbox_controller = MagicMock()

    # Set up inbox response
    mock_inbox = MagicMock()
    mock_inbox.userId = "test-id"
    mock_inbox.name = "Test Inbox"
    mock_inbox.emailAddress = "test@example.com"
    mock_inbox_controller.create_inbox.return_value = mock_inbox

    # Mock the appropriate methods
    mock_mailslurp.Configuration.return_value = mock_config
    mock_mailslurp.ApiClient.return_value.__enter__.return_value = mock_api_client
    mock_mailslurp.InboxControllerApi.return_value = mock_inbox_controller

    # Act
    user_id = "test-user-123"
    result = provision_mailbox(user_id)

    # Assert - verify mailbox is created with correct parameters
    mock_inbox_controller.create_inbox.assert_called_once()
    call_kwargs = mock_inbox_controller.create_inbox.call_args.kwargs

    assert call_kwargs["description"] == f"Mailbox assistant for user: {user_id}"
    assert call_kwargs["name"] == f"Mailbox Assistant for {user_id}"
    assert call_kwargs["useShortAddress"] is True
    assert call_kwargs["inboxType"] == "SMTP"
    assert call_kwargs["virtualInbox"] is True


@patch("app.services.mailbox_provisioning.mailslurp_client")
@patch("app.services.mailbox_provisioning.get_settings")
async def test_error_handling_during_provision(mock_settings, mock_mailslurp):
    """Test error handling when mailbox provisioning fails"""
    # Import here to avoid the initial import error
    from app.services.mailbox_provisioning import provision_mailbox

    # Configure mocks
    settings_instance = MagicMock()
    settings_instance.MAILBOX_API_KEY = "mock-api-key"
    mock_settings.return_value = settings_instance

    # Configure API client to raise an exception
    mock_mailslurp.ApiClient.return_value.__enter__.side_effect = Exception("API Error")

    # Act & Assert - verify exception is propagated
    with pytest.raises(Exception) as exc_info:
        provision_mailbox("test-user")

    assert "API Error" in str(exc_info.value)
