# backend/app/models/user_settings.py
"""The owner's choices on the settings screen (spec §10.9). Until they save, each one is the env default."""

from typing import Annotated, Literal

from beanie import Document
from pydantic import BaseModel, Field, StringConstraints

from app.config import AIProviderName, get_settings

AIModel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PollSeconds = Annotated[float, Field(ge=5, le=86_400)]  # 5 s to a day
FirstConnectDays = Annotated[int, Field(ge=1, le=365)]
# Spec §8.2: what the AI provider may see. `local_only` comes later.
PrivacyMode = Literal["full_cloud", "redacted_cloud"]


class AssistantSettings(BaseModel):
    """What the settings screen saves: all of it at once."""

    ai_provider: AIProviderName
    ai_model: AIModel
    poll_seconds: PollSeconds
    first_connect_days: FirstConnectDays
    privacy_mode: PrivacyMode


class UserSettings(Document):
    user_id: str
    # Defaults are read when a document is built, so a changed env applies until the owner saves.
    ai_provider: AIProviderName = Field(default_factory=lambda: get_settings().ai_provider)
    ai_model: AIModel = Field(default_factory=lambda: get_settings().ai_model)
    poll_seconds: PollSeconds = Field(default_factory=lambda: get_settings().sync_poll_seconds)
    first_connect_days: FirstConnectDays = Field(default_factory=lambda: get_settings().first_connect_days)
    privacy_mode: PrivacyMode = "full_cloud"

    class Settings:
        name = "user_settings"


async def settings_for(owner_id: str) -> UserSettings:
    """The owner's saved settings, else the env defaults (not stored)."""
    return await UserSettings.find_one(UserSettings.user_id == owner_id) or UserSettings(user_id=owner_id)
