# backend/app/models/webhook_security.py

from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import List


class WebhookSecurity(Document):
    api_key: str = Field(..., description="API key for authenticating webhook requests")
    allowed_ips: List[str] = Field(
        default_factory=list, description="List of allowed IP addresses"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the security config was created",
    )
    active: bool = Field(default=True, description="Whether webhook security is active")

    class Settings:
        name = "webhook_security"
