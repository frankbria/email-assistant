# backend/app/api/routers/email.py
import app.services.context_classifier as context_classifier
from app.services.email_task_mapper import map_email_to_task
import logging

from fastapi import APIRouter, Body, Request, HTTPException, status, Depends, Query
from typing import List, Optional
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

# from app.services.context_classifier import classify_context
from beanie import PydanticObjectId
from app.services.webhook_security import validate_api_key, is_ip_allowed
from app.services.duplicate_detection import is_duplicate_email
from app.utils.logging import log_security_event, track_and_alert_failed_attempt
from app.middleware import limiter, RATE_LIMIT
from app.config import get_settings
from app.utils.user_utils import get_current_user_id

router = APIRouter(prefix="/api/v1/email", tags=["email"])

logger = logging.getLogger(__name__)


@router.post("/")
async def create_email_task(
    request: Request,
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
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


@router.post("/incoming")
@limiter.limit(RATE_LIMIT)
async def incoming_email_webhook(
    request: Request,
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    actions: Optional[List[str]] = Body(None, embed=True),
):
    api_key = request.headers.get("x-api-key")
    client_ip = request.client.host if request.client else None

    # Log attempt
    log_security_event(
        event="webhook_access_attempt",
        ip_address=client_ip,
        status="attempt",
        details="Incoming webhook access attempt",
    )
    print(f"API Key: {api_key}, Client IP: {client_ip}")

    if not api_key or not client_ip:
        log_security_event(
            event="webhook_access",
            ip_address=client_ip,
            status="failure",
            details="Missing API key or client IP",
        )
        if client_ip:
            track_and_alert_failed_attempt(client_ip, "missing_api_key_or_ip")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing API key or client IP.",
        )

    if not await validate_api_key(api_key):
        log_security_event(
            event="api_key_validation",
            ip_address=client_ip,
            status="failure",
            details="Invalid API key",
        )
        if client_ip:
            track_and_alert_failed_attempt(client_ip, "invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key."
        )

    settings = get_settings()
    # Skip IP whitelist in test environment or TestClient
    if (
        client_ip != "testclient"
        and not settings.is_test
        and not await is_ip_allowed(client_ip)
    ):
        log_security_event(
            event="ip_whitelist_check",
            ip_address=client_ip,
            status="failure",
            details="IP address not allowed",
        )
        if client_ip:
            track_and_alert_failed_attempt(client_ip, "ip_not_allowed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="IP address not allowed."
        )

    log_security_event(
        event="webhook_access",
        ip_address=client_ip,
        status="success",
        details="Webhook access granted",
    )

    # Get the current user ID - for webhooks, can be passed as a query param
    user_id = await get_current_user_id(request)

    # Create the email object and check for duplicates
    email = EmailMessage(subject=subject, sender=sender, body=body, user_id=user_id)
    # Skip or flag duplicates
    if await is_duplicate_email(email):
        logger.info(f"Duplicate email detected: message_id={email.message_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Duplicate email."
        )
    # Save unique email
    await email.insert()
    logger.debug("✅ Webhook email created and saved")

    # Use centralized mapping logic (includes defaults, classification, summary)
    task = await map_email_to_task(email, actions)
    logger.debug("🔄 Mapping webhook email to task")
    await task.insert()
    logger.debug("✅ Webhook task created and saved")
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
    """Mark a specific email as not spam."""
    user_id = await get_current_user_id(request)

    email = await EmailMessage.find_one(
        {"_id": PydanticObjectId(email_id), "user_id": user_id}
    )
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    email.is_spam = False
    await email.save()
    return {"message": "Email marked as not spam", "email_id": email_id}


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
