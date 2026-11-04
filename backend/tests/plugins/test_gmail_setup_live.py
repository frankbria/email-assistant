# Gmail setup's Auto-Expunge warning (#97) against a real Gmail account: GreenMail has no such
# setting. Opt in with GMAIL_ADDRESS, GMAIL_APP_PASSWORD and GMAIL_AUTO_EXPUNGE (on|off, what the
# account is set to in Gmail → Settings → Forwarding and POP/IMAP); skipped otherwise. The check
# only adds one probe message to the Trash; it touches no other mail.
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_plugins.test_setup_checklist import gmail_plugins_yaml
from tests.utils.auth import bearer_headers
from tests.utils.gmail_account import ADDRESS_ENV, APP_KEY_ENV, GMAIL_ADDRESS, GMAIL_APP_KEY

EXPECTED = os.environ.get("GMAIL_AUTO_EXPUNGE", "")

pytestmark = pytest.mark.skipif(
    not (GMAIL_ADDRESS and GMAIL_APP_KEY and EXPECTED in ("on", "off")),
    reason=f"set {ADDRESS_ENV}, {APP_KEY_ENV} and GMAIL_AUTO_EXPUNGE=on|off to run against a real Gmail account",
)


def test_the_checklist_warns_exactly_when_auto_expunge_is_on(tmp_path, monkeypatch):
    """AC: with auto-expunge on the checklist shows the warning; with it off, it doesn't."""
    gmail_plugins_yaml(tmp_path, monkeypatch, {"MAILBOX_ACCOUNT": GMAIL_ADDRESS, "MAILBOX_PASSWORD": GMAIL_APP_KEY})

    with TestClient(app, headers=bearer_headers()) as client:
        checklist = client.post("/api/v1/connections/gmail/check").json()

    assert [step["status"] for step in checklist["steps"]] == ["done"] * 5
    auto_expunge = [warning for warning in checklist["warnings"] if "Auto-Expunge is on" in warning]
    assert len(auto_expunge) == (1 if EXPECTED == "on" else 0), checklist["warnings"]
    assert not [warning for warning in checklist["warnings"] if "couldn't check" in warning.lower()]
