# app/services/onboarding.py
from app.services.mailbox_provisioning import provision_mailbox
from app.models.user_settings import UserSettings


# create a new emailbox for a new user
#### create the mailbox and retrieve the settings (mailbox name, user name, password)
# (/servies/mailbox_provisioning.py)
def create_mailbox(user_id: str) -> dict:
    """
    Create a new mailbox for the user and store the settings in the database.
    """
    # Provision a new mailbox using the MailSlurp API
    mailbox_info = provision_mailbox(user_id)

    # Store the mailbox settings in the database use default values for the settings for now.
    user_settings = UserSettings(
        user_id=user_id,
        incoming_email_address=mailbox_info["email_address"],
    )
    user_settings.save()

    return mailbox_info


# change the emailbox adddress for an existing user


# reset the emailbox login for an existing user
