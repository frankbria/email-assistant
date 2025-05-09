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
from httpx import AsyncClient


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


## connect MailSlurp webhook (NEW_MAIL) to this endpoint
@router.post("/incoming")
@limiter.limit(RATE_LIMIT)
async def incoming_email_webhook(
    request: Request,
    sender: str = Body(..., embed=True),
    subject: str = Body("", embed=True),  # Default to empty string instead of required
    body: str = Body("", embed=True),  # Default to empty string instead of required
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


# ===================TEMPORARY IMAP FUNCTIONALITY====================


@router.get("/get/{address}")
async def get_email_by_address(address: str, request: Request):
    """Fetch an email by its address."""
    # Build an IMAP request to fetch the email
    # This is a placeholder for the actual implementation
    # temp IMAP functionality
    from imapclient import IMAPClient
    from email import message_from_bytes

    IMAP_HOST = get_settings().imap_host
    IMAP_PORT = get_settings().imap_port
    IMAP_USERNAME = address
    IMAP_PASSWORD = get_settings().imap_password

    # Login to the IMAP server
    # shut off the rate limiter for each of these emails

    api_key = get_settings().emergency_webhook_api_key

    #   request.app.state.limited.enabled = False
    print("Checking emails... with api_key: " + api_key)

    try:
        with IMAPClient(host=IMAP_HOST, ssl=True) as client:
            client.login(IMAP_USERNAME, IMAP_PASSWORD)
            client.select_folder("INBOX", readonly=False)
            # Search for the email by address
            uids = client.search(["UNSEEN"])
            for uid in uids:
                raw = client.fetch(uid, ["RFC822"])[uid][b"RFC822"]
                msg = message_from_bytes(raw)
                print("Subject: " + msg.get("Subject"))
                print("From: " + msg.get("From"))
                print("To: " + msg.get("To"))
                # call the /incoming API endpoint to process the email
                # override the rate limit for this endpoint

                # 1. Pick out the plain‑text part:
                body = None
                if msg.is_multipart():
                    for part in msg.walk():
                        # skip attachments
                        content_dispo = part.get("Content-Disposition", "")
                        if (
                            part.get_content_type() == "text/plain"
                            and "attachment" not in content_dispo
                        ):
                            payload = part.get_payload(decode=True)  # bytes
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
                else:
                    # not multipart — the payload *is* the body
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

                if body is None:
                    # fallback if you really need something
                    body = msg.get_payload()  # might be a str or list

                print("Body: " + body)

                # Now pass `body` safely to your webhook:
                async with AsyncClient() as api_client:
                    response = await api_client.post(
                        "http://localhost:8000/api/v1/email/incoming",
                        json={
                            "sender": msg.get("From"),
                            "subject": msg.get("Subject"),
                            "body": body,
                        },
                        headers={
                            "x-api-key": api_key,
                            "X-Forwarded-For": "192.168.0.1",
                        },
                    )
                    if response.status_code != 200:
                        logger.error(f"Error sending email to webhook: {response.text}")
                """
                await incoming_email_webhook(
                    request=request,
                    sender=msg.get("From"),
                    subject=msg.get("Subject"),
                    body=body,
                )
                """
                # Mark the email as seen
                # TODO: delete the email after processing
                client.add_flags(uid, ["\\Seen"])

        return {"message": "Success"}
    except Exception as e:
        logger.error(f"Error fetching email: {e}")
        raise HTTPException(status_code=500, detail="Error fetching email")
    finally:
        #        request.app.state.limited.enabled = True
        print("Done")


# ===================END TEMPORARY IMAP FUNCTIONALITY====================


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

    # Create task for the email now that it's no longer marked as spam
    task = await map_email_to_task(email)
    if task:
        await task.insert()
        return {"message": "Email marked as not spam and task created", "email_id": email_id, "task_id": str(task.id)}

    # Return default message if no task was created
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
