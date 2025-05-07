# backend/app/api/routers/admin.py

from fastapi import APIRouter, HTTPException, status, Body, Depends, Request
from app.models.webhook_security import WebhookSecurity
from typing import List, Optional
from pydantic import BaseModel
from app.utils.user_utils import get_current_user_id

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# Placeholder admin dependency (replace with real auth in future)
async def admin_required(request: Request):
    # In production, check user roles/permissions here
    # For now, we'll just ensure they have a user_id
    user_id = await get_current_user_id(request)
    # TODO: Add admin role verification when auth is implemented
    return True


class WebhookSecurityUpdate(BaseModel):
    api_key: Optional[str] = None
    allowed_ips: Optional[List[str]] = None
    active: Optional[bool] = None


@router.get("/webhook/security", response_model=Optional[WebhookSecurity])
async def get_webhook_security_config(
    request: Request, admin: bool = Depends(admin_required)
):
    # For future multi-tenant support, we could filter by organization/tenant
    # user_id = await get_current_user_id(request)

    config = await WebhookSecurity.find_one(WebhookSecurity.active == True)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active webhook security config found.",
        )
    return config


@router.post("/webhook/security", response_model=WebhookSecurity)
async def update_webhook_security_config(
    request: Request,
    update: WebhookSecurityUpdate,
    admin: bool = Depends(admin_required),
):
    # For future multi-tenant support, we could filter by organization/tenant
    # user_id = await get_current_user_id(request)

    config = await WebhookSecurity.find_one(WebhookSecurity.active == True)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active webhook security config found.",
        )
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    await config.save()
    return config
