# A digest (spec §4): low-priority mail gathers into one rolling digest job, one summary line per message; finishing
# it archives every message, and undoing that archive restores them all. Real MongoDB; GreenMail + the reference IMAP
# plugin; FakeAIProvider proposing `digest`; real SyncEngine passes after an empty first pass.
import pytest

from app.models.job import Job
from app.models.rule import Rule
from app.pipeline.proposal import Proposal
from tests.test_routes.test_corrections_api import sync_pass
from tests.test_routes.test_history_api import history
from tests.test_sync.test_inbox_sync import add_owner
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
NEWSLETTERS = ("news@garden.example", "weekly@cooking.example", "digest@cycling.example")
DIGEST = Proposal(needs_owner=False, verb="digest", title="This week's newsletter", evidence=["This week in"],
                  digest="Three short stories about the season.", noise_rationale="A newsletter", confidence=0.9)


async def three_newsletters_in_one_digest(test_db, mailbox: Mailbox, plugins) -> Job:
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")  # the owner's voice is read from it
    ai = FakeAIProvider(DIGEST)
    await sync_pass(test_db, plugins, ai)  # first connect, so the newsletters aren't first-connect mail (§5.3)
    for sender in NEWSLETTERS:
        mailbox.deliver(sender=sender, subject=f"News from {sender}", body="This week in brief: three short stories.")
    await sync_pass(test_db, plugins, ai)
    [digest] = await Job.find(Job.owner_id == OWNER_ID).to_list()
    return digest


async def test_ac_three_newsletters_become_one_digest_and_done_archives_all_three(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)

    assert (digest.verb, digest.state, len(digest.message_ids)) == ("digest", "open", 3)
    assert digest.artifacts.digest is not None
    assert digest.artifacts.digest.splitlines() == [f"{sender}: Three short stories about the season." for sender in NEWSLETTERS]

    approved = await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json={})

    assert approved.status_code == 200 and (approved.json()["state"], approved.json()["error"]) == ("done", None)
    assert mailbox.messages("INBOX") == [] and len(mailbox.messages("Archive")) == 3


async def test_undoing_the_digests_archive_restores_all_three(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json={})
    [archive] = await history(async_client)
    assert (archive["action"], len(archive["message_ids"])) == ("archived", 3)

    undone = await async_client.post(f"/api/v1/history/{archive['_id']}/undo")

    assert undone.status_code == 200 and undone.json()["ok"]
    assert len(mailbox.messages("INBOX")) == 3 and mailbox.messages("Archive") == []



async def test_newsletters_after_the_digest_was_finished_start_a_new_one(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json={})
    mailbox.deliver(sender=NEWSLETTERS[0], subject="Next week's news", body="This week in brief: two short stories.")

    await sync_pass(test_db, plugins, FakeAIProvider(DIGEST))

    [fresh] = await Job.find(Job.owner_id == OWNER_ID, Job.state == "open").to_list()
    assert fresh.id != digest.id and len(fresh.message_ids) == 1 and fresh.verb == "digest"


async def test_mail_of_a_stream_that_asks_first_makes_the_digest_it_joins_wait_for_the_owner(test_db, mailbox, plugins):
    """§10.4: the owner restored this stream's mail before, so the digest it joins is never archived without a tap."""
    await Rule(owner_id=OWNER_ID, match="sender", value=NEWSLETTERS[1], verb=None, ask_first=True).insert()

    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)

    assert len(digest.message_ids) == 3 and digest.requires_approval
