import secrets
from typing import List, Optional
from app.models.webhook_security import WebhookSecurity


async def validate_api_key(provided_key: str) -> bool:
    """Check if the provided API key matches an active stored key."""
    # Find an active config matching the provided API key
    config = await WebhookSecurity.find_one(
        {
            "active": True,
            "api_key": provided_key,
        }
    )
    return config is not None


async def is_ip_allowed(ip_address: str) -> bool:
    """Check if the given IP address is allowed by an active config."""
    # Find an active config that includes the IP address in its whitelist
    config = await WebhookSecurity.find_one(
        {
            "active": True,
            "allowed_ips": ip_address,
        }
    )
    return config is not None


def generate_secure_api_key(length: int = 40) -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(length)
