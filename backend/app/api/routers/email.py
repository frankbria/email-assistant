# backend/app/api/routers/email.py
import app.services.context_classifier as context_classifier

from fastapi import APIRouter, Body
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

# from app.services.context_classifier import classify_context
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

    # Apply defaulting rules for sender and subject
    sender_val = sender.strip() if sender and sender.strip() else "Unknown Sender"
    subject_val = subject.strip() if subject and subject.strip() else "(No Subject)"
    # Determine context using AI or rule-based classifier
    context_label = await context_classifier.classify_context(subject_val, body)
    # Compute summary: use subject_val if body empty, otherwise subject_val + truncated snippet
    trimmed_body = body.strip()
    if not trimmed_body:
        summary_text = subject_val
    else:
        snippet = trimmed_body[:100] + ("…" if len(trimmed_body) > 100 else "")
        summary_text = f"{subject_val}: {snippet}"
    # Build task arguments, omitting `actions` if not provided so default actions apply
    task_kwargs = {
        "email": email,
        "sender": sender_val,
        "subject": subject_val,
        "context": context_label,
        "summary": summary_text,
    }
    if actions is not None:
        task_kwargs["actions"] = actions
    task = AssistantTask(**task_kwargs)
    await task.insert()

    return {"email_id": str(email.id), "task_id": str(task.id)}
