# backend/app/utils/logging.py

import logging
from datetime import datetime
from typing import Optional
from collections import defaultdict
from threading import Lock
import time
import os

logger = logging.getLogger("security")

# Configure security logger if not already configured
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

ALERT_FAILURE_THRESHOLD = int(os.getenv("SECURITY_ALERT_FAILURE_THRESHOLD", 5))
ALERT_WINDOW_SECONDS = int(
    os.getenv("SECURITY_ALERT_WINDOW_SECONDS", 600)
)  # 10 min default

_failed_attempts = defaultdict(list)  # ip -> [timestamps]
_failed_attempts_lock = Lock()


def alert_suspicious_activity(ip_address: str, reason: str):
    """
    Send an alert for suspicious activity (e.g., repeated failures from the same IP).
    For demo: log at WARNING level. In production, send email, webhook, etc.
    """
    logger.warning(f"ALERT: Suspicious activity from IP {ip_address}: {reason}")


def track_and_alert_failed_attempt(ip_address: str, reason: str):
    """
    Track failed attempts and alert if threshold is exceeded.
    """
    now = time.time()
    with _failed_attempts_lock:
        attempts = _failed_attempts[ip_address]
        attempts.append(now)
        # Remove old attempts
        _failed_attempts[ip_address] = [
            t for t in attempts if now - t < ALERT_WINDOW_SECONDS
        ]
        if len(_failed_attempts[ip_address]) >= ALERT_FAILURE_THRESHOLD:
            alert_suspicious_activity(ip_address, reason)


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
