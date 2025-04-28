# backend/app/api/routers/email.py
import app.services.context_classifier as context_classifier
from app.services.email_task_mapper import map_email_to_task
import logging

from fastapi import APIRouter, Body
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

# from app.services.context_classifier import classify_context
from beanie import PydanticObjectId

router = APIRouter(prefix="/api/v1/email", tags=["email"])

logger = logging.getLogger(__name__)


@router.post("/")
async def create_email_task(
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    actions: Optional[List[str]] = Body(None, embed=True),
):
    logger.debug("🔄 Creating email task in API")
    # Create and save the email, then map to a task
    email = EmailMessage(subject=subject, sender=sender, body=body)
    await email.insert()
    logger.debug("✅ Email created and saved")

    # Use centralized mapping logic (includes defaults, classification, summary)
    task = await map_email_to_task(email, actions)
    logger.debug("🔄 Mapping email to task")
    await task.insert()
    logger.debug("✅ Task created and saved")
    return {"email_id": str(email.id), "task_id": str(task.id)}
