# Calibration (spec §10.7): a dry run of the pipeline over recent mail that takes no action, and the owner's reactions
# on the ask-owner card, which become examples, optionally rules, and lines of a local, git-ignored test set.
# Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider.
import json
import subprocess
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.main import app
from app.models.action_log import ActionLogEntry
from app.models.example import Example
from app.models.job import Job
from app.models.message import Message
from app.permissions import PermissionSettings
from app.pipeline.proposal import Proposal
from tests.test_routes.test_corrections_api import rules
from tests.test_sync.test_inbox_sync import PLUGIN
from tests.utils.auth import OWNER_ID
from tests.utils.mail_server import Mailbox, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
BACKEND = Path(__file__).resolve().parents[2]
DEALS = "This week only: 20% off garden tools. Shop now before it ends."
NOISE = Proposal(needs_owner=False, verb="archive_noise", title="The shop's weekly garden tools deals",
                 evidence=["garden tools"], noise_rationale="A promotional mailing", confidence=0.9)


@pytest.fixture
def test_set() -> Iterator[Path]:
    """A test set beside the default one, so the git-ignore check covers the real location."""
    path = BACKEND / Path(Settings().test_set_file).parent / f"pytest-{uuid.uuid4().hex}.jsonl"
    app.dependency_overrides[get_settings] = lambda: Settings(test_set_file=str(path))
    yield path
    app.dependency_overrides.pop(get_settings)
    path.unlink(missing_ok=True)


async def stored(sender: Mailbox, mailbox: Mailbox, subject: str, age: timedelta) -> Message:
    """A synced inbox message: `sender` mailed `mailbox`, the owner's account."""
    ref = sender.deliver_to(mailbox, subject=subject, body=DEALS)
    message = Message.model_validate({
        "owner_id": OWNER_ID, "plugin_id": PLUGIN, "ref": ref, "message_id": ref, "sender": {"email": sender.address},
        "to": [{"email": mailbox.address}], "cc": [], "date": datetime.now(UTC) - age, "subject": subject,
        "snippet": DEALS, "pipeline_done": True,
    })
    await message.insert()
    return message


async def test_a_calibration_run_takes_no_action_on_the_mail(async_client, test_db, mailbox, plugins, ai):
    """AC (#92): zero plugin writes. Noise is autonomous, so the live pipeline would archive this mail on its own."""
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    shop = new_mailbox()
    older = await stored(shop, mailbox, "Weekly deals #1", timedelta(days=2))
    newer = await stored(shop, mailbox, "Weekly deals #2", timedelta(days=1))
    ai.result = NOISE

    started = await async_client.post("/api/v1/calibration", params={"sample": 2})

    assert started.status_code == 202
    assert len(mailbox.messages("INBOX")) == 2 and mailbox.messages("Archive") == []
    assert await ActionLogEntry.find_all().count() == 0 and await Job.find_all().count() == 0
    cards = (await async_client.get("/api/v1/calibration")).json()
    assert [card["subject"] for card in cards] == ["Weekly deals #2", "Weekly deals #1"]
    assert [card["job"]["message_ids"] for card in cards] == [[str(newer.id)], [str(older.id)]]
    # The AI's verb is the card's one-tap answer (the owner's 👍); anything else is a fix.
    assert all((card["job"]["ask_owner"], card["job"]["suggested_verbs"]) == (True, ["archive_noise"]) for card in cards)


async def test_the_sample_is_the_newest_mail(async_client, test_db, mailbox, plugins, ai):
    shop = new_mailbox()
    await stored(shop, mailbox, "Old deals", timedelta(days=9))
    await stored(shop, mailbox, "New deals", timedelta(days=1))
    ai.result = NOISE

    await async_client.post("/api/v1/calibration", params={"sample": 1})

    assert [card["subject"] for card in (await async_client.get("/api/v1/calibration")).json()] == ["New deals"]


async def test_a_reaction_teaches_and_joins_the_git_ignored_test_set(async_client, test_db, mailbox, plugins, ai, test_set):
    shop = new_mailbox()
    message = await stored(shop, mailbox, "Weekly deals", timedelta(days=1))
    ai.result = NOISE.model_copy(update={"verb": "reply", "draft": "Thanks, not now.", "noise_rationale": None})
    await async_client.post("/api/v1/calibration")
    [card] = (await async_client.get("/api/v1/calibration")).json()

    reacted = await async_client.post(f"/api/v1/calibration/{card['job']['_id']}/react", json={"verb": "archive_noise", "always": True})

    assert reacted.status_code == 200 and reacted.json()["state"] == "done"
    assert (await async_client.get("/api/v1/calibration")).json() == []
    [example] = await Example.find(Example.owner_id == OWNER_ID).to_list()
    assert (example.message_id, example.verb, example.source) == (message.id, "archive_noise", "calibration")
    assert await rules() == [("sender", shop.address.lower(), "archive_noise")]
    [line] = test_set.read_text().splitlines()
    entry = json.loads(line)
    assert (entry["message_id"], entry["proposed"], entry["owner_verb"]) == (message.message_id, "reply", "archive_noise")
    assert DEALS in entry["text"]
    ignored = subprocess.run(["git", "check-ignore", "-q", str(test_set)], cwd=BACKEND)
    assert ignored.returncode == 0, f"{test_set} would be committed"
    assert len(mailbox.messages("INBOX")) == 1 and await ActionLogEntry.find_all().count() == 0
    again = await async_client.post(f"/api/v1/calibration/{card['job']['_id']}/react", json={"verb": "reply"})
    assert again.status_code == 404


async def test_a_reaction_without_always_teaches_no_rule(async_client, test_db, mailbox, plugins, ai, test_set):
    await stored(new_mailbox(), mailbox, "Weekly deals", timedelta(days=1))
    ai.result = NOISE
    await async_client.post("/api/v1/calibration")
    [card] = (await async_client.get("/api/v1/calibration")).json()

    await async_client.post(f"/api/v1/calibration/{card['job']['_id']}/react", json={"verb": "archive_noise"})

    assert await rules() == [] and await Example.find_all().count() == 1
    assert json.loads(test_set.read_text())["owner_verb"] == "archive_noise"
