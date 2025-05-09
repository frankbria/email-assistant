from mailslurp_client import Configuration, InboxControllerApi, EmailControllerApi
from app.config import get_settings


def get_inbox_id_from_email_address(email_address: str) -> str:
    """
    Extracts the inbox ID from a given email address.
    """
    if not email_address:
        return ""
    # Example: user1@example.com -> user1
    return InboxControllerApi.get_inbox_id_from_email_address(email_address)


def get_emails_from_inbox(inbox_id: str) -> list:
    """
    Retrieves emails from a specific inbox using the MailSlurp API.
    """
    if not inbox_id:
        return []
    # Example: Fetch emails from the specified inbox
    config = Configuration()
    api_instance = InboxControllerApi(config)
    try:
        thread = api_instance.get_emails(inbox_id)
        result = thread.get()
        return result
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []


def get_emails_from_email_address(email_address: str) -> list:
    """
    Retrieves emails from a specific email address using the MailSlurp API.
    """
    if not email_address:
        return []
    # Example: Fetch emails from the specified email address
    config = Configuration()
    api_instance = InboxControllerApi(config)
    try:
        thread = api_instance.get_emails_from_email_address(email_address)
        result = thread.get()
        return result
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []
