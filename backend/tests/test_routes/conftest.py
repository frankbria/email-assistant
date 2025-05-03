# backend/tests/test_routes/conftest.py

import pytest
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.webhook_security import WebhookSecurity
from app.models.user_settings import UserSettings

@pytest.fixture
async def setup_test_data(db_transaction):
    """Populate test DB with basic records for each test."""
    email = EmailMessage(
        subject="Test Email", sender="test@example.com", body="This is a test email"
    )
    await email.insert()

    task = AssistantTask(
        email=email,
        context="test",
        summary="Test task summary",
        actions=["action1", "action2"],
        status="pending",
    )
    await task.insert()

    webhook = WebhookSecurity(
        api_key="test_key",
        allowed_ips=["127.0.0.1"],
        active=True,
    )
    await webhook.insert()

    yield

    # No need to clean up test data; each test runs in its own transaction
    # await EmailMessage.find_all().delete()
    # await AssistantTask.find_all().delete()
    # await WebhookSecurity.find_all().delete()
