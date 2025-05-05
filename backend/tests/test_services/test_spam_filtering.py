import pytest
from app.models.email_message import EmailMessage
from app.services.duplicate_detection import is_spam_email


@pytest.mark.parametrize(
    "email_subject, email_body, expected",
    [
        ("Win a prize", "Click here to claim your free money", True),
        ("Meeting tomorrow", "Let's discuss the project updates", False),
        ("Limited time offer", "Urgent offer just for you", True),
        ("Hello", "This is a normal email", False),
    ],
)
def test_is_spam_email(email_subject, email_body, expected):
    email = EmailMessage(
        subject=email_subject, body=email_body, sender="test@example.com"
    )
    assert is_spam_email(email) == expected
