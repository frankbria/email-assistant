# A digest (spec §4): low-priority mail gathers into one rolling digest job, one summary line per message; finishing
# it archives every message, and undoing that archive restores them all. Real MongoDB; GreenMail + the reference IMAP
# plugin; FakeAIProvider proposing `digest`; real SyncEngine passes after an empty first pass.
import pytest
from fastapi import HTTPException

from app.api.routers.jobs import archive_as_noise, replace_proposal
from app.models.example import Example
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.models.rule import Rule
from app.pipeline.proposal import Proposal
from app.pipeline.run import join_open_digest
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


def seen(digest: Job) -> dict[str, list[str]]:
    """What the owner's card showed when they tapped: a digest's action speaks only for those messages."""
    return {"message_ids": [str(message_id) for message_id in digest.message_ids]}


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

    approved = await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json=seen(digest))

    assert approved.status_code == 200 and (approved.json()["state"], approved.json()["error"]) == ("done", None)
    assert mailbox.messages("INBOX") == [] and len(mailbox.messages("Archive")) == 3


async def test_undoing_the_digests_archive_restores_all_three(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json=seen(digest))
    [archive] = await history(async_client)
    assert (archive["action"], len(archive["message_ids"])) == ("archived", 3)

    undone = await async_client.post(f"/api/v1/history/{archive['_id']}/undo")

    assert undone.status_code == 200 and undone.json()["ok"]
    assert len(mailbox.messages("INBOX")) == 3 and mailbox.messages("Archive") == []



async def test_newsletters_after_the_digest_was_finished_start_a_new_one(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json=seen(digest))
    mailbox.deliver(sender=NEWSLETTERS[0], subject="Next week's news", body="This week in brief: two short stories.")

    await sync_pass(test_db, plugins, FakeAIProvider(DIGEST))

    [fresh] = await Job.find(Job.owner_id == OWNER_ID, Job.state == "open").to_list()
    assert fresh.id != digest.id and len(fresh.message_ids) == 1 and fresh.verb == "digest"


async def test_mail_of_a_stream_that_asks_first_makes_the_digest_it_joins_wait_for_the_owner(test_db, mailbox, plugins):
    """§10.4: the owner restored this stream's mail before, so the digest it joins is never archived without a tap."""
    await Rule(owner_id=OWNER_ID, match="sender", value=NEWSLETTERS[1], verb=None, ask_first=True).insert()

    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)

    assert len(digest.message_ids) == 3 and digest.requires_approval


@pytest.mark.parametrize(("method", "path", "body"), [
    ("post", "choose", {"verb": "reply"}),
    ("post", "correct", {"kind": "noise"}),
    ("post", "correct", {"kind": "wrong_action", "verb": "todo"}),
    ("patch", "", {"link": "https://x.example"}),
])
async def test_a_digest_of_several_messages_refuses_actions_meant_for_one_message(
    async_client, test_db, mailbox, plugins, ai, method, path, body
):
    """Another action, a correction or an edit would act on the first message alone while done archives them all."""
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)

    response = await getattr(async_client, method)(f"/api/v1/jobs/{digest.id}/{path}".rstrip("/"), json=body)

    assert response.status_code == 409
    assert response.json()["detail"] == "a digest speaks for several messages; approve or dismiss it, or archive them one by one"
    assert await Job.get(digest.id) == digest
    assert len(mailbox.messages("INBOX")) == 3 and mailbox.messages("Archive") == []
    assert await Rule.find_all().to_list() == [] and await Example.find_all().to_list() == []


async def test_the_first_line_of_a_digest_without_a_summary_has_no_blank_line_before_it(test_db, mailbox, plugins):
    """An open digest carrying only a reason (no summary yet) gains its first line without a leading newline."""
    await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    [digest] = await Job.find_all().to_list()
    await Job.find(Job.id == digest.id).update({"$set": {"artifacts.digest": None}})
    newcomer = Job(owner_id=OWNER_ID, verb="digest", title="t", artifacts=Artifacts(digest="A short story."),
                   message_ids=digest.message_ids[:1])

    joined = await join_open_digest(newcomer, await message_of_digest(digest))

    assert joined.artifacts.digest == f"{NEWSLETTERS[0]}: A short story."


async def message_of_digest(digest: Job) -> Message:
    message = await Message.get(digest.message_ids[0])
    assert message is not None
    return message


async def test_the_history_of_a_digests_archive_names_its_message_count(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json=seen(digest))
    await Message.find(Message.id == digest.message_ids[0]).delete()  # the first message is gone; the entry stays

    [card] = (await async_client.get("/api/v1/history")).json()

    assert (card["entry"]["action"], card["subject"]) == ("archived", "3 messages")
    assert card["sender"]["email"] == NEWSLETTERS[1]


async def test_a_sender_name_that_looks_like_a_field_reference_is_kept_as_text(test_db, mailbox, plugins):
    """Untrusted mail text must never be read as a MongoDB expression: '$x' would erase the digest so far."""
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    message = await message_of_digest(digest)
    message.sender.name = "$artifacts.missing"
    newcomer = Job(owner_id=OWNER_ID, verb="digest", title="t", artifacts=Artifacts(digest="A short story."),
                   message_ids=digest.message_ids[:1])

    joined = await join_open_digest(newcomer, message)

    assert joined.artifacts.digest == f"{digest.artifacts.digest}\n$artifacts.missing: A short story."


async def test_a_proposal_is_not_stored_over_a_job_whose_messages_changed_while_it_was_made(test_db, mailbox, plugins):
    """A newsletter joining while the AI drafted a reply for a one-message digest: the reply would speak for both."""
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    snapshot = digest.model_copy(update={"message_ids": digest.message_ids[:2]})
    reply = Job(owner_id=OWNER_ID, verb="reply", title="Answer", artifacts=Artifacts(draft="Thanks"), message_ids=snapshot.message_ids)

    with pytest.raises(HTTPException) as refused:
        await replace_proposal(snapshot, reply)

    assert refused.value.status_code == 409
    assert (await Job.get(digest.id)).verb == "digest"


async def test_a_noise_correction_is_not_stored_over_a_job_whose_messages_changed_meanwhile(test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    snapshot = digest.model_copy(update={"message_ids": digest.message_ids[:1]})

    with pytest.raises(HTTPException) as refused:
        await archive_as_noise(snapshot, await message_of_digest(digest), plugins)

    assert refused.value.status_code == 409
    assert (await Job.get(digest.id)).verb == "digest" and len(mailbox.messages("INBOX")) == 3


async def test_approving_a_digest_that_gathered_more_mail_since_it_was_shown_archives_nothing(async_client, test_db, mailbox, plugins):
    """A newsletter that joined after the owner's card was drawn was never reviewed, so the tap doesn't cover it."""
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)
    shown = digest.model_copy(update={"message_ids": digest.message_ids[:2]})

    approved = await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json=seen(shown))
    dismissed = await async_client.post(f"/api/v1/jobs/{digest.id}/dismiss", json=seen(shown))

    assert (approved.status_code, dismissed.status_code) == (409, 409)
    assert (await Job.get(digest.id)).state == "open" and len(mailbox.messages("INBOX")) == 3


async def test_a_digest_is_only_finished_for_the_messages_the_owner_saw(async_client, test_db, mailbox, plugins):
    digest = await three_newsletters_in_one_digest(test_db, mailbox, plugins)

    unsaid = await async_client.post(f"/api/v1/jobs/{digest.id}/approve", json={})
    dismissed = await async_client.post(f"/api/v1/jobs/{digest.id}/dismiss", json=seen(digest))

    assert unsaid.status_code == 422
    assert dismissed.status_code == 200 and len(mailbox.messages("Archive")) == 3


async def test_copies_of_one_email_in_two_accounts_are_one_message_to_the_guard(async_client, test_db, mailbox, plugins):
    """An ask-owner digest whose mail also arrived in another account still lets the owner choose an action."""
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")
    await sync_pass(test_db, plugins, FakeAIProvider(DIGEST))
    mailbox.deliver(sender="news@garden.example", subject="Spring", body="This week in the garden: planting tips.")
    await sync_pass(test_db, plugins, FakeAIProvider(DIGEST))
    [job] = await Job.find_all().to_list()
    original = await Message.get(job.message_ids[0])
    copy = original.model_copy(update={"id": None, "plugin_id": "other-account"})
    await copy.insert()
    await Job.find(Job.id == job.id).update({"$set": {"ask_owner": True}, "$push": {"message_ids": copy.id}})

    chosen = await async_client.patch(f"/api/v1/jobs/{job.id}", json={"options": ["a"]})

    assert chosen.status_code == 200
