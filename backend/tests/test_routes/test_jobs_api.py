# The jobs API behind the job queue (spec §10.1, §10.2): list the owner's open jobs; approve, edit, choose another
# action, dismiss. Real MongoDB; GreenMail + the reference IMAP plugin for sends and archives; FakeAIProvider.
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId

from app.api.routers.jobs import plugin_registry
from app.main import app
from app.models.job import Artifacts, Job, JobState, Verb
from app.models.message import Message
from app.permissions import ApprovalStreak
from app.pipeline.proposal import Proposal
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import get_ai_provider
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import PLUGIN, connected
from tests.utils.auth import OWNER_ID, bearer_headers
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox, new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
QUESTION = "Could we meet Thursday at 3pm?"


@pytest.fixture
async def plugins(mailbox: Mailbox) -> AsyncIterator[PluginRegistry]:
    mailbox.create_folder("Archive")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        app.dependency_overrides[plugin_registry] = lambda: registry
        yield registry
    app.dependency_overrides.pop(plugin_registry)


@pytest.fixture
def ai() -> Iterator[FakeAIProvider]:
    provider = FakeAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider)


async def job_from(
    sender: Mailbox, mailbox: Mailbox, verb: Verb, artifacts: Artifacts | None = None, owner_id: str = OWNER_ID, **fields: object
) -> Job:
    """A job over a real message: `sender` mailed `mailbox`, the owner's account."""
    ref = sender.deliver_to(mailbox, subject="Q4 budget", body=QUESTION)
    message = Message.model_validate({
        "owner_id": owner_id, "plugin_id": PLUGIN, "ref": ref, "message_id": ref, "sender": {"name": "Ana", "email": sender.address},
        "to": [{"email": mailbox.address}], "cc": [], "date": datetime.now(UTC), "subject": "Q4 budget", "snippet": "",
    })
    await message.insert()
    assert message.id is not None
    job = Job(owner_id=owner_id, verb=verb, title="Ana asks to meet Thursday", evidence=[QUESTION],
              artifacts=artifacts or Artifacts(), message_ids=[message.id], **fields)
    await job.insert()
    return job


def archived(mailbox: Mailbox) -> bool:
    return mailbox.messages("INBOX") == [] and len(mailbox.messages("Archive")) == 1


async def streak(verb: str) -> int:
    found = await ApprovalStreak.find_one(ApprovalStreak.owner_id == OWNER_ID, ApprovalStreak.verb == verb)
    return found.in_a_row if found else 0


async def test_the_queue_lists_the_owners_open_and_failed_jobs_newest_first_with_sender_and_subject(async_client, test_db, mailbox):
    ana = new_mailbox()
    older = await job_from(ana, mailbox, "todo", Artifacts(link="https://x.example"), created_at=datetime.now(UTC) - timedelta(hours=1))
    failed = await job_from(ana, mailbox, "reply", Artifacts(draft="Yes"), state="failed", error="send failed — retry: down")
    for hidden_state in ("done", "dismissed", "snoozed", "handled_elsewhere"):
        await job_from(ana, mailbox, "todo", state=hidden_state)
    await job_from(ana, mailbox, "todo", owner_id="someone-else")

    response = await async_client.get("/api/v1/jobs")

    assert response.status_code == 200
    cards = response.json()
    assert [card["job"]["_id"] for card in cards] == [str(failed.id), str(older.id)]
    assert cards[0]["sender"] == {"name": "Ana", "email": ana.address} and cards[0]["subject"] == "Q4 budget"
    assert cards[0]["job"]["error"] == "send failed — retry: down" and cards[1]["job"]["evidence"] == [QUESTION]


async def test_approving_a_reply_sends_it_archives_the_mail_and_counts_toward_promotion(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Thursday at 3 works."))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["permission_level"]) == ("done", "ask")
    [reply] = ana.messages("INBOX")
    assert reply["Subject"] == "Re: Q4 budget" and "Thursday at 3 works." in reply.get_content()
    assert archived(mailbox) and await streak("reply") == 1


async def test_an_edited_draft_is_what_gets_sent_and_restarts_the_promotion_streak(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Sure."))
    await ApprovalStreak(owner_id=OWNER_ID, verb="reply", in_a_row=4).insert()

    edited = await async_client.patch(f"/api/v1/jobs/{job.id}", json={"draft": "Thursday at 3 works. See you!"})
    approved = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert edited.status_code == 200 and edited.json()["edited"] is True
    assert edited.json()["artifacts"]["draft"] == "Thursday at 3 works. See you!"
    assert approved.json()["state"] == "done"
    assert "Thursday at 3 works. See you!" in ana.messages("INBOX")[0].get_content()
    assert await streak("reply") == 0


async def test_an_edit_changes_only_the_fields_sent(async_client, test_db, mailbox):
    due = datetime(2026, 12, 1, 9, tzinfo=UTC)
    job = await job_from(new_mailbox(), mailbox, "todo", Artifacts(link="https://pay.example/invoice"))

    response = await async_client.patch(f"/api/v1/jobs/{job.id}", json={"due": due.isoformat()})

    stored = await Job.get(job.id)
    assert response.status_code == 200 and stored is not None
    assert stored.artifacts.link == "https://pay.example/invoice" and stored.due is not None
    assert stored.due.replace(tzinfo=UTC) == due and stored.edited


async def test_a_forward_goes_to_the_recipient_the_owner_confirmed(async_client, test_db, mailbox, plugins):
    ben = new_mailbox()
    job = await job_from(new_mailbox(), mailbox, "forward", Artifacts(draft="FYI, see below.", forward_to="someone@ai.example"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={"forward_to": ben.address})

    assert response.json()["state"] == "done"
    [forwarded] = ben.messages("INBOX")
    assert forwarded["Subject"] == "Fwd: Q4 budget" and QUESTION in forwarded.get_content()


async def test_a_forward_without_a_confirmed_recipient_fails_and_stays_in_the_queue(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "forward", Artifacts(draft="FYI.", forward_to="someone@ai.example"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["error"]) == ("failed", "send failed — retry: choose who to forward it to")
    assert len(mailbox.messages("INBOX")) == 1 and await streak("forward") == 0


async def test_approving_a_snooze_hides_the_job_until_its_date(async_client, test_db, mailbox, plugins):
    due = datetime.now(UTC) + timedelta(days=3)
    job = await job_from(new_mailbox(), mailbox, "snooze", due=due)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert (response.json()["state"], response.json()["permission_level"]) == ("snoozed", "ask")
    assert await streak("snooze") == 1


@pytest.mark.parametrize("verb", ["todo", "archive_noise", "digest"])
async def test_approving_a_todo_or_noise_finishes_it_and_archives_the_mail(async_client, test_db, mailbox, plugins, verb):
    job = await job_from(new_mailbox(), mailbox, verb, Artifacts(link="https://x.example", noise_rationale="a newsletter"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert response.json()["state"] == "done" and archived(mailbox)


@pytest.mark.parametrize(("fields", "status", "detail"), [
    ({"verb": "todo", "ask_owner": True}, 409, "choose an action for this mail first"),
    ({"verb": "unsubscribe"}, 422, "unsubscribing isn't available yet"),
    ({"verb": "snooze"}, 422, "needs a date to wait for"),
    ({"verb": "todo", "state": "done"}, 409, "isn't open"),
])
async def test_an_approval_that_cant_act_says_why(async_client, test_db, mailbox, plugins, fields, status, detail):
    job = await job_from(new_mailbox(), mailbox, **fields)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/approve", json={})

    assert response.status_code == status and detail in response.json()["detail"]
    assert len(mailbox.messages("INBOX")) == 1


@pytest.mark.parametrize("state", ["open", "failed"])
async def test_dismissing_a_job_archives_its_mail(async_client, test_db, mailbox, plugins, state: JobState):
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Yes"), state=state)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/dismiss")

    assert response.json()["state"] == "dismissed" and archived(mailbox)
    assert await streak("reply") == 0  # a dismissal isn't an approval


async def test_choosing_another_action_proposes_it_for_that_verb(async_client, test_db, mailbox, plugins, ai):
    job = await job_from(new_mailbox(), mailbox, "todo", ask_owner=True, suggested_verbs=["todo"], problems=["the AI isn't confident"])
    ai.result = Proposal(needs_owner=True, verb="reply", title="Ana asks to meet Thursday at 3pm", evidence=[QUESTION],
                         draft="Thursday at 3 works.", confidence=0.9)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "reply"})

    chosen = response.json()
    assert response.status_code == 200
    assert (chosen["verb"], chosen["ask_owner"], chosen["problems"]) == ("reply", False, [])
    assert chosen["artifacts"]["draft"] == "Thursday at 3 works." and chosen["title"] == "Ana asks to meet Thursday at 3pm"
    assert "already decided: reply" in ai.prompts[0]  # the owner's verb, fixed in the schema and the prompt


async def test_a_chosen_action_the_ai_cant_ground_stays_with_the_owner_and_says_why(async_client, test_db, mailbox, plugins, ai):
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Yes"))
    ai.result = Proposal(needs_owner=False, verb="todo", title="Pay the invoice", evidence=["text that isn't in the mail"],
                         link="https://pay.example", confidence=0.9)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "todo"})

    chosen = response.json()
    assert (chosen["verb"], chosen["ask_owner"], chosen["suggested_verbs"]) == ("todo", True, ["todo"])
    assert "evidence not in the email: \"text that isn't in the mail\"" in chosen["problems"]
    assert chosen["artifacts"]["draft"] is None and chosen["edited"] is False


@pytest.mark.parametrize(("method", "action"), [("post", "approve"), ("post", "dismiss"), ("post", "choose"), ("patch", "")])
async def test_someone_elses_job_isnt_found_and_a_malformed_id_is_rejected(async_client, test_db, mailbox, plugins, ai, method, action):
    theirs = await job_from(new_mailbox(), mailbox, "todo", owner_id="someone-else")
    body = {"verb": "todo"} if action == "choose" else {}

    for job_id, status in ((theirs.id, 404), (PydanticObjectId(), 404), ("not-an-id", 422)):
        path = f"/api/v1/jobs/{job_id}/{action}".rstrip("/")
        response = await async_client.request(method.upper(), path, json=body)
        assert response.status_code == status, (path, response.text)


async def test_each_owner_sees_only_their_own_jobs(async_client, test_db, mailbox):
    mine = await job_from(new_mailbox(), mailbox, "todo")
    await job_from(new_mailbox(), mailbox, "todo", owner_id="someone-else")

    response = await async_client.get("/api/v1/jobs", headers=bearer_headers("someone-else"))
    own = await async_client.get("/api/v1/jobs")

    assert len(response.json()) == 1 and response.json()[0]["job"]["owner_id"] == "someone-else"
    assert [card["job"]["_id"] for card in own.json()] == [str(mine.id)]


async def test_the_old_tasks_routes_are_gone(async_client, test_db):
    assert (await async_client.get("/api/v1/tasks/")).status_code == 404
    assert (await async_client.patch(f"/api/v1/tasks/{PydanticObjectId()}", json={"status": "done"})).status_code == 404
