# backend/app/api/routers/permissions.py
"""The settings screen's permissions section (spec §9): each verb's level with its ceiling, changes
checked against the ceilings, and the promotion offer after unedited approvals."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import OwnerId
from app.models.job import PermissionLevel
from app.permissions import (
    CEILINGS,
    DEFAULTS,
    PermissionSettings,
    PermissionsRejected,
    answer_promotion,
    is_level,
    level_for,
    promotion_offers,
    set_levels,
)

router = APIRouter(prefix="/api/v1/permissions", tags=["permissions"])


def permissions_path(request: Request) -> Path:
    return Path(request.app.state.settings.permissions_file)


class VerbPermission(BaseModel):
    verb: str
    level: PermissionLevel
    default: PermissionLevel
    ceiling: PermissionLevel
    reason: str  # why the ceiling is where it is


class Permissions(BaseModel):
    verbs: list[VerbPermission]
    file_error: str | None  # why permissions.yaml was rejected or couldn't be written
    promotions: list[str]  # verbs offered promotion to autonomous, waiting for an answer


class LevelChoice(BaseModel):
    level: str  # checked by the ceilings, so a wrong value gets the same plain explanation


class PromotionAnswer(BaseModel):
    accept: bool


async def current(owner_id: str) -> Permissions:
    settings = await PermissionSettings.find_one(PermissionSettings.owner_id == owner_id)
    verbs = [
        VerbPermission(verb=verb, level=await level_for(owner_id, verb), default=DEFAULTS[verb], ceiling=ceiling, reason=reason)
        for verb, (ceiling, reason) in CEILINGS.items()
    ]
    return Permissions(verbs=verbs, file_error=settings.file_error if settings else None, promotions=await promotion_offers(owner_id))


@router.get("", response_model=Permissions)
async def get_permissions(owner_id: OwnerId) -> Permissions:
    return await current(owner_id)


@router.put("/{verb}", response_model=Permissions)
async def set_permission(verb: str, choice: LevelChoice, owner_id: OwnerId, path: Path = Depends(permissions_path)) -> Permissions:
    try:
        if not is_level(choice.level):
            raise PermissionsRejected(f"{verb}: {choice.level!r} isn't a level (autonomous, ask or never_auto)")
        await set_levels(owner_id, {verb: choice.level}, path)
    except PermissionsRejected as rejected:
        raise HTTPException(status_code=422, detail=str(rejected)) from rejected
    return await current(owner_id)


@router.post("/promotions/{verb}", response_model=Permissions)
async def answer_promotion_offer(
    verb: str, answer: PromotionAnswer, owner_id: OwnerId, path: Path = Depends(permissions_path)
) -> Permissions:
    if not await answer_promotion(owner_id, verb, answer.accept, path):
        raise HTTPException(status_code=404, detail=f"No promotion is waiting for {verb}")
    return await current(owner_id)
