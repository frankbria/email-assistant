# The owner's answer on an ask-owner card (spec §10.2) is kept as an example, and "always do this for this
# sender/list" also teaches a rule, effective on the next message from that stream.
# Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider; a real SyncEngine pass.
import logging
from collections.abc import Iterator

import pytest
from beanie import PydanticObjectId

from app.main import app
from app.models.example import Example
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.models.rule import Rule
from app.permissions import PermissionSettings
from app.pipeline.proposal import Proposal
from app.services.ai_provider import get_ai_provider
from tests.test_routes.test_corrections_api import DEALS, SHOP, newest_job, rules, sync_pass
from tests.test_routes.test_jobs_api import QUESTION, job_from
from tests.test_sync.test_inbox_sync import add_owner
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")


class UnsureAI(FakeAIProvider):
    """Unaided it leaves the shop's deals to the owner. Once the verb is fixed (by the owner's choice or a rule),
    it fills in that verb's details, as a real model does."""

    async def propose(self, prompt, schema):
        unsure = Proposal(
            needs_owner=True,
            verb="reply",
            title="The shop's garden tools offer",
            evidence=["garden tools"],
            draft="Thanks, not now.",
            confidence=0.4,
        )
        noise = Proposal(
            needs_owner=False,
            verb="archive_noise",
            title="The shop's weekly garden tools deals",
            evidence=["garden tools"],
            noise_rationale="A promotional mailing",
            confidence=0.9,
        )
        self.result = unsure if schema is Proposal else noise
        return await super().propose(prompt, schema)


@pytest.fixture
def unsure_ai() -> Iterator[UnsureAI]:
    """The same fake for the sync passes and for the API's /choose."""
    provider = UnsureAI()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider)


async def ask_owner_job_from_the_shop(test_db, mailbox, plugins, ai: FakeAIProvider) -> Job:
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")  # the owner's voice is read from it
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "ask"}).insert()
    mailbox.deliver(sender=SHOP, subject="Weekly deals", body=DEALS.format(percent=20))
    await sync_pass(test_db, plugins, ai)
    asked = await newest_job()
    assert asked.ask_owner
    return asked


async def test_choosing_always_for_a_sender_decides_their_next_message_without_asking(async_client, test_db, mailbox, plugins, unsure_ai):
    """AC (#84): after "always" for sender S, the next message from S skips the ask-owner card and gets the chosen verb."""
    ai = unsure_ai
    asked = await ask_owner_job_from_the_shop(test_db, mailbox, plugins, ai)

    chosen = await async_client.post(f"/api/v1/jobs/{asked.id}/choose", json={"verb": "archive_noise", "always": True})

    assert chosen.status_code == 200 and chosen.json()["verb"] == "archive_noise"
    assert await rules() == [("sender", SHOP, "archive_noise")]
    mailbox.deliver(sender=SHOP, subject="Weekly deals #2", body=DEALS.format(percent=30))
    await sync_pass(test_db, plugins, ai)
    after = await newest_job()
    assert after.id != asked.id
    assert (after.verb, after.ask_owner) == ("archive_noise", False)


async def test_a_choice_without_always_is_an_example_but_not_a_rule(async_client, test_db, mailbox, plugins, unsure_ai):
    ai = unsure_ai
    asked = await ask_owner_job_from_the_shop(test_db, mailbox, plugins, ai)

    chosen = await async_client.post(f"/api/v1/jobs/{asked.id}/choose", json={"verb": "archive_noise"})

    assert chosen.status_code == 200
    assert await rules() == []
    [example] = await Example.find(Example.owner_id == OWNER_ID).to_list()
    assert (example.message_id, example.verb, example.source) == (asked.message_ids[0], "archive_noise", "ask_owner")
    mailbox.deliver(sender=SHOP, subject="Weekly deals #2", body=DEALS.format(percent=30))
    await sync_pass(test_db, plugins, ai)
    assert (await newest_job()).ask_owner


async def test_another_action_chosen_for_a_proposed_job_isnt_an_ask_owner_answer(async_client, test_db, mailbox, plugins, ai):
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Yes"))
    ai.result = Proposal(
        needs_owner=False,
        verb="todo",
        title="Book the Thursday meeting room",
        evidence=[QUESTION],
        link="https://rooms.example",
        confidence=0.9,
    )

    response = await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "todo", "always": True})

    assert response.status_code == 200 and response.json()["verb"] == "todo"
    assert await Example.find_all().count() == 0 and await rules() == []


async def test_always_on_a_list_message_teaches_a_rule_for_the_list(async_client, test_db, mailbox, plugins, ai):
    job = await job_from(new_mailbox(), mailbox, "todo", ask_owner=True, suggested_verbs=["todo"])
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "Garden deals <Deals.Shop.Example>"}})
    ai.result = Proposal(
        needs_owner=False,
        verb="todo",
        title="Book the Thursday meeting room",
        evidence=[QUESTION],
        link="https://rooms.example",
        confidence=0.9,
    )

    await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "todo", "always": True})

    assert await rules() == [("list_id", "deals.shop.example", "todo")]


async def test_always_for_a_list_leaves_a_broader_sender_rule_alone(async_client, test_db, mailbox, plugins, ai):
    """The checkbox names the list, so the rule keys on the list, even when a sender rule decided this message."""
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "todo", ask_owner=True, suggested_verbs=["todo"])
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "Garden deals <Deals.Shop.Example>"}})
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address.lower(), verb="reply").insert()
    ai.result = Proposal(
        needs_owner=False,
        verb="todo",
        title="Book the Thursday meeting room",
        evidence=[QUESTION],
        link="https://rooms.example",
        confidence=0.9,
    )

    await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "todo", "always": True})

    assert sorted(await rules()) == [("list_id", "deals.shop.example", "todo"), ("sender", ana.address.lower(), "reply")]


async def test_the_queue_says_which_list_a_card_s_mail_came_from(async_client, test_db, mailbox):
    job = await job_from(new_mailbox(), mailbox, "todo", ask_owner=True)
    await job_from(new_mailbox(), mailbox, "todo")
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "Garden deals <deals.shop.example>"}})

    cards = (await async_client.get("/api/v1/jobs")).json()

    assert sorted(card["list_id"] or "" for card in cards) == ["", "Garden deals <deals.shop.example>"]


async def test_a_lesson_that_fails_to_store_still_returns_the_chosen_job(async_client, test_db, mailbox, plugins, ai, caplog):
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "todo", ask_owner=True, suggested_verbs=["todo"])
    ai.result = Proposal(
        needs_owner=False,
        verb="todo",
        title="Book the Thursday meeting room",
        evidence=[QUESTION],
        link="https://rooms.example",
        confidence=0.9,
    )
    examples = Example.get_pymongo_collection().name
    # MongoDB itself refuses every example write, as a full disk or a broken collection would.
    await test_db.command("collMod", examples, validator={"source": {"$in": []}}, validationAction="error")
    try:
        with caplog.at_level(logging.ERROR, logger="app.api.routers.jobs"):
            response = await async_client.post(f"/api/v1/jobs/{job.id}/choose", json={"verb": "todo", "always": True})
    finally:
        await test_db.command("collMod", examples, validator={})

    assert response.status_code == 200 and response.json()["verb"] == "todo"
    assert "Couldn't record the example" in caplog.text
    # the lessons stand apart: an example that can't be stored still leaves the rule the owner asked for
    assert await rules() == [("sender", ana.address.lower(), "todo")]


async def test_a_choice_that_isnt_made_teaches_nothing(async_client, test_db, mailbox, plugins, ai):
    theirs = await job_from(new_mailbox(), mailbox, "todo", owner_id="someone-else", ask_owner=True)
    finished = await job_from(new_mailbox(), mailbox, "todo", state="done", ask_owner=True)
    body = {"verb": "todo", "always": True}

    for job_id, status in ((theirs.id, 404), (PydanticObjectId(), 404), (finished.id, 409)):
        response = await async_client.post(f"/api/v1/jobs/{job_id}/choose", json=body)
        assert response.status_code == status

    assert await Rule.find_all().count() == 0 and await Example.find_all().count() == 0
