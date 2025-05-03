# backend/tests/test_services/conftest.py

import pytest
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.webhook_security import WebhookSecurity
from app.models.user_settings import UserSettings


@pytest.fixture(scope="function")
async def set_webhook_security(db_transaction):
    """Set up a valid webhook security configuration."""
    config = WebhookSecurity(api_key="validkey", allowed_ips=["127.0.0.1"], active=True)
    await config.insert()

    yield
