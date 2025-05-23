# backend/app/api/routers/settings.py

from fastapi import APIRouter, HTTPException, Depends, Body, Request
from typing import Optional
from app.models.user_settings import UserSettings
from pydantic import BaseModel, Field, ValidationError
from beanie import PydanticObjectId
from beanie.operators import Eq
from app.utils.user_utils import get_current_user_id

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


# Pydantic model for PATCH payload
class UpdateEmailSettings(BaseModel):
    enable_spam_filtering: Optional[bool] = Field(None)
    enable_auto_categorization: Optional[bool] = Field(None)
    skip_low_priority_emails: Optional[bool] = Field(None)


@router.get("/email", response_model=UserSettings)
async def get_email_settings(request: Request):
    user_id = await get_current_user_id(request)
    settings = await UserSettings.find_one(UserSettings.user_id == user_id)
    if not settings:
        # Sensible defaults for first-time users
        settings = UserSettings(user_id=user_id)
        await settings.insert()
    return settings


@router.patch("/email", response_model=UserSettings)
async def update_email_settings(
    request: Request, payload: UpdateEmailSettings = Body(...)
):
    try:
        user_id = await get_current_user_id(request)
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=400, detail="No fields provided for update."
            )
        settings = await UserSettings.find(
            UserSettings.user_id == user_id
        ).first_or_none()
        if not settings:
            settings = UserSettings(user_id=user_id)
        for key, value in update_data.items():
            setattr(settings, key, value)
        await settings.save()
        return settings
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {ve.errors()}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update settings: {str(e)}"
        )
