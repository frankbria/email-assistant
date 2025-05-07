# backend/app/utils/user_utils.py

from typing import Optional
from fastapi import Request
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"


async def get_current_user_id(request: Optional[Request] = None) -> str:
    """
    Get the current user ID from the request context.

    Currently returns a default user ID, but will be updated to extract from Clerk JWT
    when authentication is implemented.

    Args:
        request: The FastAPI request object, which may contain user context

    Returns:
        str: The user ID string
    """
    # TODO: When Clerk authentication is implemented, extract user_id from the JWT token
    # if request and request.headers.get("authorization"):
    #     token = request.headers.get("authorization").split(" ")[1]
    #     # Implement JWT validation and extraction here
    #     # user_id = validate_and_extract_user_id(token)
    #     # return user_id

    # For now, get a user_id from query parameters for demo purposes (if provided)
    if request and request.query_params.get("user_id"):
        return request.query_params.get("user_id")

    # Otherwise use a default user ID
    settings = get_settings()
    return (
        settings.DEFAULT_USER_ID
        if hasattr(settings, "DEFAULT_USER_ID")
        else DEFAULT_USER_ID
    )
