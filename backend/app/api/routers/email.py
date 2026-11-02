# backend/app/api/routers/email.py
from app.services.email_task_mapper import map_email_to_task
import logging

from fastapi import APIRouter, Body, Request, HTTPException
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

from beanie import PydanticObjectId
from app.utils.user_utils import get_current_user_id


router = APIRouter(prefix="/api/v1/email", tags=["email"])

logger = logging.getLogger(__name__)


@router.post("/")
async def create_email_task(
    request: Request,
    sender: str = Body(..., embed=True),
    subject: str = Body("", embed=True),  # Default to empty string instead of required
    body: str = Body("", embed=True),  # Default to empty string instead of required
    actions: Optional[List[str]] = Body(None, embed=True),
):
    logger.debug("🔄 Creating email task in API")
    # Get the current user ID
    user_id = await get_current_user_id(request)

    # Create and save the email, then map to a task
    email = EmailMessage(subject=subject, sender=sender, body=body, user_id=user_id)
    await email.insert()
    logger.debug("✅ Email created and saved")

    # Use centralized mapping logic (includes defaults, classification, summary)
    task = await map_email_to_task(email, actions)
    logger.debug("🔄 Mapping email to task")
    await task.insert()
    logger.debug("✅ Task created and saved")
    return {"email_id": str(email.id), "task_id": str(task.id)}




@router.get("/spam")
async def get_spam_emails(request: Request):
    """Fetch all emails flagged as spam."""
    user_id = await get_current_user_id(request)

    spam_emails = await EmailMessage.find(
        {"$and": [{"is_spam": True}, {"is_archived": False}, {"user_id": user_id}]}
    ).to_list()

    return spam_emails


@router.patch("/{email_id}/not-spam")
async def mark_email_as_not_spam(email_id: str, request: Request):
    """Mark a specific email as not spam and ensure it gets full AI processing."""
    user_id = await get_current_user_id(request)

    email = await EmailMessage.find_one(
        {"_id": PydanticObjectId(email_id), "user_id": user_id}
    )
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Update email status
    email.is_spam = False
    await email.save()

    # Check for existing task
    existing_task = await AssistantTask.find_one({"email_id": str(email.id)})

    # Process the email with AI, ensuring full processing
    new_task = await map_email_to_task(
        email, skipSpamCheck=True, forceFullProcessing=True
    )

    if not new_task:
        return {
            "message": "Email marked as not spam, but task creation failed",
            "email_id": email_id,
        }

    if existing_task:
        # Update existing task with new AI-processed data
        existing_task.subject = new_task.subject  # Use new AI-summarized subject
        existing_task.context = new_task.context  # Update context classification
        existing_task.description = new_task.description  # Update with AI summary
        existing_task.priority = new_task.priority  # Recalculate priority
        existing_task.actions = new_task.actions  # Update suggested actions

        await existing_task.save()
        return {
            "message": "Email marked as not spam and task updated with AI processing",
            "email_id": email_id,
            "task_id": str(existing_task.id),
        }
    else:
        # No existing task, just insert the new one
        await new_task.insert()
        return {
            "message": "Email marked as not spam and task created",
            "email_id": email_id,
            "task_id": str(new_task.id),
        }


@router.patch("/{email_id}/archive")
async def archive_email(email_id: str, request: Request):
    """Mark an email as archived (dismissed from spam view)."""
    user_id = await get_current_user_id(request)

    email = await EmailMessage.find_one(
        {"_id": PydanticObjectId(email_id), "user_id": user_id}
    )
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    email.is_archived = True
    await email.save()
    return {"message": "Email archived", "email_id": email_id}
