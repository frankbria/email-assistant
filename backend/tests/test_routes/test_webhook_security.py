# backend/tests/test_routes/test_webhook_security.py

import pytest
from app.models.webhook_security import WebhookSecurity
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_webhook_incoming_rejects_without_api_key(
    async_client, set_webhook_security
):
    # No API key header
    response = await async_client.post(
        "/api/v1/email/incoming",
        json={"sender": "a@b.com", "subject": "s", "body": "b"},
    )
    assert response.status_code == 400
    assert "Missing API key" in response.text


@pytest.mark.asyncio
async def test_webhook_incoming_rejects_invalid_api_key(
    async_client, set_webhook_security
):
    # Invalid API key header
    response = await async_client.post(
        "/api/v1/email/incoming",
        headers={"x-api-key": "wrongkey"},
        json={"sender": "a@b.com", "subject": "s", "body": "b"},
    )
    assert response.status_code == 403
    assert "Invalid API key" in response.text


@pytest.mark.asyncio
async def test_webhook_incoming_rejects_blocked_ip(
    async_client, set_webhook_security, monkeypatch
):
    # Patch client.host to simulate a blocked IP
    class FakeClient:
        host = "8.8.8.8"

    monkeypatch.setattr(
        "starlette.requests.Request.client", property(lambda self: FakeClient)
    )
    response = await async_client.post(
        "/api/v1/email/incoming",
        headers={"x-api-key": "validkey"},
        json={"sender": "a@b.com", "subject": "s", "body": "b"},
    )
    assert response.status_code == 403
    assert "IP address not allowed" in response.text


@pytest.mark.dependency(depends=["set_webhook_security"])
@pytest.mark.asyncio
async def test_webhook_incoming_accepts_valid(
    async_client, set_webhook_security, monkeypatch
):

    # Patch client.host to simulate allowed IP
    class FakeClient:
        host = "127.0.0.1"

    monkeypatch.setattr(
        "starlette.requests.Request.client", property(lambda self: FakeClient)
    )
    response = await async_client.post(
        "/api/v1/email/incoming",
        headers={"x-api-key": "validkey"},
        json={"sender": "a@b.com", "subject": "s", "body": "b"},
    )
    assert response.status_code == 200
    assert "email_id" in response.text and "task_id" in response.text
