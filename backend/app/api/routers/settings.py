# backend/app/api/routers/settings.py
"""The settings screen (spec §10.9): AI provider and model, poll interval, first-connect window and privacy mode."""

from fastapi import APIRouter, Request

from app.auth import OwnerId
from app.models.user_settings import AssistantSettings, UserSettings, settings_for
from app.sync import SyncEngine

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
async def get_settings(owner_id: OwnerId) -> UserSettings:
    return await settings_for(owner_id)


@router.put("", response_model=UserSettings)
async def save_settings(choice: AssistantSettings, owner_id: OwnerId, request: Request) -> UserSettings:
    settings = await settings_for(owner_id)
    for field, value in choice.model_dump().items():
        setattr(settings, field, value)
    await settings.save()
    sync: SyncEngine | None = getattr(request.app.state, "sync", None)  # None until the app has started
    if sync is not None:  # a pass now, which then waits the new interval: no restart needed
        sync.wake.set()
    return settings
