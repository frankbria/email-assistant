# backend/tests/test_services/test_webhook_security_application.py

import pytest
from app.models.webhook_security import WebhookSecurity
from app.services.webhook_security import (
    validate_api_key,
    is_ip_allowed,
    generate_secure_api_key,
)


@pytest.mark.asyncio
async def test_validate_api_key_valid_and_invalid(test_db):
    # Insert a test config
    config = WebhookSecurity(api_key="testkey123", allowed_ips=["1.2.3.4"], active=True)
    await config.insert()

    # Valid key
    assert await validate_api_key("testkey123") is True
    # Invalid key
    assert await validate_api_key("wrongkey") is False


@pytest.mark.asyncio
async def test_is_ip_allowed_allowed_and_blocked(test_db):
    config = WebhookSecurity(
        api_key="irrelevant", allowed_ips=["10.0.0.1", "127.0.0.1"], active=True
    )
    await config.insert()

    # Allowed IP
    assert await is_ip_allowed("10.0.0.1") is True
    # Blocked IP
    assert await is_ip_allowed("8.8.8.8") is False


@pytest.mark.asyncio
async def test_validate_api_key_no_active_config():
    # No config in DB
    assert await validate_api_key("anykey") is False


@pytest.mark.asyncio
async def test_is_ip_allowed_no_active_config():
    # No config in DB
    assert await is_ip_allowed("1.2.3.4") is False


@pytest.mark.asyncio
async def test_generate_secure_api_key_length():
    key = generate_secure_api_key(32)
    assert isinstance(key, str)
    assert len(key) >= 32  # token_urlsafe may be longer than requested
