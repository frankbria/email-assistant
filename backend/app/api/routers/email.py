# backend/app/api/routers/email.py
from fastapi import APIRouter, Body
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.context_classifier import classify_context
from beanie import PydanticObjectId

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.post("/")
async def create_email_task(
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    actions: Optional[List[str]] = Body(None, embed=True),
):
    # Create and save the email
    email = EmailMessage(subject=subject, sender=sender, body=body)
    await email.insert()

    # Determine context using AI or rule-based classifier
    context_label = await classify_context(subject, body)
    # Create task with classified context and actions (if provided)
    task = AssistantTask(
        email=email,
        context=context_label,
        summary=body,  # Use email body as initial summary
        actions=actions,  # None will fall back to default actions
    )
    await task.insert()

    return {"email_id": str(email.id), "task_id": str(task.id)}
