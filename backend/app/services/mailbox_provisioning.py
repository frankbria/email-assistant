# app/services/mailbox_provisioning.py

import mailslurp_client
from app.config import get_settings
from app.models.user_settings import UserSettings


mailbox_api = get_settings().mailbox_api_key


def provision_mailbox(user_id: str) -> dict:
    """
    Provision a new mailbox for the user and store the settings in the database.
    """
    # Initialize the MailSlurp client
    configuration = mailslurp_client.Configuration()
    configuration.api_key["x-api-key"] = mailbox_api

    with mailslurp_client.ApiClient(configuration) as api_client:
        inbox_controller = mailslurp_client.InboxControllerApi(api_client)
        inbox = inbox_controller.create_inbox(
            description="Mailbox assistant for user: " + user_id,
            name="Mailbox Assistant for " + user_id,
            useShortAddress=True,
            inboxType="SMTP",
            virtualInbox=True,
        )

    return {
        "mailbox_id": inbox.userId,
        "mailbox_name": inbox.name,
        "email_address": inbox.emailAddress,
    }
