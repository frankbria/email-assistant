# backend/app/api/routers/email.py
from fastapi import APIRouter, Body
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
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

    # Create task with email context and actions (if provided)
    task = AssistantTask(
        email=email,
        context=subject,  # Use email subject as initial context
        summary=body,  # Use email body as initial summary
        actions=actions,  # This will be None if not provided, triggering model defaults
    )
    await task.insert()

    return {"email_id": str(email.id), "task_id": str(task.id)}
