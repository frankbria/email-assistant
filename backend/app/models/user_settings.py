# backend/app/models/user_settings.py

from beanie import Document
from pydantic import Field
from typing import Optional


class UserSettings(Document):
    user_id: str = Field(..., description="Unique identifier for the user")
    enable_spam_filtering: bool = Field(
        default=True, description="Enable or disable spam filtering"
    )
    enable_auto_categorization: bool = Field(
        default=True, description="Enable or disable auto-categorization"
    )
    skip_low_priority_emails: bool = Field(
        default=False, description="Skip low-priority emails in the UI"
    )

    class Settings:
        name = "user_settings"
