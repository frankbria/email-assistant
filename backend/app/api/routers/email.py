# backend/app/api/routers/email.py
from fastapi import APIRouter, Body
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.post("/")
async def create_email_task(
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
):
    email = EmailMessage(subject=subject, sender=sender, body=body)
    await email.insert()
    task = AssistantTask(email=email)
    await task.insert()
    return {"email_id": str(email.id), "task_id": str(task.id)}
