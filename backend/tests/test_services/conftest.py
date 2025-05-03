# backend/tests/test_services/conftest.py

import pytest
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.webhook_security import WebhookSecurity
from app.models.user_settings import UserSettings
