# backend/app/api/routers/email.py
import app.services.context_classifier as context_classifier
from app.services.email_task_mapper import map_email_to_task
import logging

from fastapi import APIRouter, Body, Request, HTTPException, status, Depends
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

    # Create the email object and check for duplicates
    email = EmailMessage(subject=subject, sender=sender, body=body)
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
