# backend/app/utils/logging.py

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("security")

# Configure security logger if not already configured
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_security_event(
    event: str,
    ip_address: Optional[str] = None,
    status: str = "success",
    user: Optional[str] = None,
    details: Optional[str] = None,
):
    """
    Log a security-related event.
    :param event: Description of the event (e.g., 'webhook_access', 'api_key_validation')
    :param ip_address: IP address involved in the event
    :param status: 'success' or 'failure'
    :param user: Optional user identifier
    :param details: Optional additional details (avoid sensitive data)
    """
    log_msg = f"event={event} status={status}"
    if ip_address:
        log_msg += f" ip={ip_address}"
    if user:
        log_msg += f" user={user}"
    if details:
        log_msg += f" details={details}"
    logger.info(log_msg)
