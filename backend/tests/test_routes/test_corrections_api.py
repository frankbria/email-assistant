# Corrections on jobs (spec §10.4, AC-2.3): "wrong action", "this is noise" and "this isn't noise" each put the
# job right and teach a rule for its sender or list, effective on the next matching message, plus an example.
# Real MongoDB; GreenMail + the reference IMAP plugin; FakeAIProvider.
import logging

import pytest
from beanie import PydanticObjectId

from app.models.example import Example
from app.models.job import Artifacts, Job
from app.models.message import Message
from app.models.rule import Rule
from app.permissions import PermissionSettings
from app.pipeline.proposal import Proposal
from app.plugins.registry import PluginRegistry
from app.sync import SyncEngine
from tests.test_routes.test_history_api import history
from tests.test_routes.test_jobs_api import QUESTION, archived, job_from
from tests.test_sync.test_inbox_sync import add_owner
from tests.utils.auth import OWNER_ID
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import new_mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
SHOP = "deals@shop.example"
DEALS = "This week only: {percent}% off garden tools. Shop now before it ends."


class RuleFollowingAI(FakeAIProvider):
    """Unaided it takes the shop's deals for mail to answer. When a rule fixes the verb (structured output then
    allows only that verb), it fills in that verb's details, as a real model does."""

    async def propose(self, prompt, schema):
        unaided = Proposal(needs_owner=False, verb="reply", title="Answer the shop's garden tools offer",
                           evidence=["garden tools"], draft="Thanks, not now.", confidence=0.8)
        noise = Proposal(needs_owner=False, verb="archive_noise", title="The shop's weekly garden tools deals",
                         evidence=["garden tools"], noise_rationale="A promotional mailing", confidence=0.9)
        self.result = unaided if schema is Proposal else noise
        return await super().propose(prompt, schema)


async def sync_pass(test_db, plugins: PluginRegistry, provider: FakeAIProvider) -> None:
    await SyncEngine(plugins, test_db["user"], poll_seconds=60, ai_provider_for=provider).sync_all()


async def newest_job() -> Job:
    job = await Job.find(Job.owner_id == OWNER_ID).sort("-created_at").first_or_none()
    assert job is not None
    return job


async def rules() -> list[tuple[str, str, str]]:
    return [(rule.match, rule.value, rule.verb) for rule in await Rule.find(Rule.owner_id == OWNER_ID).to_list()]


@pytest.mark.parametrize("noise_level", ["ask", "autonomous"])
async def test_ac_2_3_mail_from_a_sender_corrected_to_noise_is_handled_as_noise_across_ten_repeats(
    async_client, test_db, mailbox, plugins, noise_level
):
    """AC-2.3. The rule fixes the verb, so every repeat is an archive_noise job, never an ask-owner card; whether the
    app then archives it without a tap is archive_noise's permission (§9): `ask` waits for the owner's approval."""
    await add_owner(test_db, OWNER_ID)
    mailbox.create_folder("Sent")  # the owner's voice is read from it
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": noise_level}).insert()
    ai = RuleFollowingAI()
    mailbox.deliver(sender=SHOP, subject="Weekly deals", body=DEALS.format(percent=20))
    await sync_pass(test_db, plugins, ai)
    proposed = await newest_job()
    assert proposed.verb == "reply"

    corrected = await async_client.post(f"/api/v1/jobs/{proposed.id}/correct", json={"kind": "noise"})

    assert corrected.status_code == 200 and corrected.json()["state"] == "done"
    assert mailbox.messages("INBOX") == []
    for repeat in range(10):
        mailbox.deliver(sender=SHOP, subject=f"Weekly deals #{repeat}", body=DEALS.format(percent=30 + repeat))
        await sync_pass(test_db, plugins, ai)
        job = await newest_job()
        assert (job.verb, job.ask_owner, job.artifacts.noise_rationale) == ("archive_noise", False, "A promotional mailing"), repeat
        assert "already decided: archive_noise" in ai.prompts[-1]
        if noise_level == "autonomous":
            assert job.state == "done" and mailbox.messages("INBOX") == [], repeat
        else:
            assert job.state == "open" and len(mailbox.messages("INBOX")) == repeat + 1, repeat
    assert len(ai.prompts) == 11  # one call per message: the rule decides, the AI only fills in the details


async def test_this_is_noise_archives_the_mail_and_learns_a_sender_rule_and_an_example(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Yes"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})

    corrected = response.json()
    assert response.status_code == 200
    assert (corrected["state"], corrected["verb"], corrected["artifacts"]["draft"]) == ("done", "archive_noise", None)
    assert archived(mailbox)
    assert await rules() == [("sender", ana.address.lower(), "archive_noise")]
    [example] = await Example.find(Example.owner_id == OWNER_ID).to_list()
    assert (example.message_id, example.verb, example.source) == (job.message_ids[0], "archive_noise", "correction")
    [entry] = await history(async_client)
    assert (entry["action"], entry["by"], entry["permission_level"], entry["undoable"]) == ("archived", "owner", "ask", True)


async def test_a_wrong_action_proposes_the_right_verb_and_updates_the_senders_rule_rather_than_adding_one(
    async_client, test_db, mailbox, plugins, ai
):
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb="todo").insert()
    job = await job_from(ana, mailbox, "todo", Artifacts(link="https://x.example"))
    ai.result = Proposal(needs_owner=False, verb="reply", title="Ana asks to meet Thursday at 3pm", evidence=[QUESTION],
                         draft="Thursday at 3 works.", confidence=0.9)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "wrong_action", "verb": "reply"})

    corrected = response.json()
    assert response.status_code == 200
    assert (corrected["verb"], corrected["ask_owner"], corrected["state"]) == ("reply", False, "open")
    assert corrected["artifacts"] == {**Artifacts().model_dump(), "draft": "Thursday at 3 works."}
    assert "already decided: reply" in ai.prompts[0]
    assert await rules() == [("sender", ana.address.lower(), "reply")]
    [example] = await Example.find(Example.owner_id == OWNER_ID).to_list()
    assert (example.verb, example.source) == ("reply", "correction")


async def test_a_message_from_a_list_is_corrected_for_the_list(async_client, test_db, mailbox, plugins):
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Yes"))
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "Garden deals <Deals.Shop.Example>"}})

    await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})

    assert await rules() == [("list_id", "deals.shop.example", "archive_noise")]


async def test_this_isnt_noise_forgets_the_noise_rule_and_hands_the_mail_to_the_owner(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb="archive_noise").insert()
    job = await job_from(ana, mailbox, "archive_noise", Artifacts(noise_rationale="A promotional mailing"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "not_noise"})

    corrected = response.json()
    assert response.status_code == 200
    assert (corrected["state"], corrected["ask_owner"], corrected["suggested_verbs"]) == ("open", True, [])
    assert corrected["problems"] == ["you said this isn't noise"] and corrected["artifacts"]["noise_rationale"] is None
    assert await rules() == []
    assert len(mailbox.messages("INBOX")) == 1
    assert await history(async_client) == []  # nothing was done to the mail


async def test_this_isnt_noise_keeps_a_rule_that_isnt_about_noise(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb="reply").insert()
    job = await job_from(ana, mailbox, "archive_noise", Artifacts(noise_rationale="A promotional mailing"))

    await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "not_noise"})

    assert await rules() == [("sender", ana.address.lower(), "reply")]


@pytest.mark.parametrize(("verb", "body", "detail"), [
    ("reply", {"kind": "not_noise"}, "this job isn't noise"),
    ("reply", {"kind": "wrong_action"}, "say which action is right"),
    ("reply", {"kind": "guess"}, None),
])
async def test_a_correction_that_doesnt_fit_the_job_is_refused_and_teaches_nothing(
    async_client, test_db, mailbox, plugins, ai, verb, body, detail
):
    job = await job_from(new_mailbox(), mailbox, verb, Artifacts(draft="Yes"))

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json=body)

    assert response.status_code == 422
    if detail:
        assert detail in str(response.json()["detail"])
    assert await rules() == [] and await Example.find_all().count() == 0


@pytest.mark.parametrize("body", [{"kind": "noise"}, {"kind": "not_noise"}, {"kind": "wrong_action", "verb": "todo"}])
async def test_a_finished_job_cant_be_corrected(async_client, test_db, mailbox, plugins, ai, body):
    job = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="A promotional mailing"), state="done")

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json=body)

    assert response.status_code == 409
    assert await rules() == [] and await Example.find_all().count() == 0


@pytest.mark.parametrize("body", [{"kind": "noise"}, {"kind": "not_noise"}, {"kind": "wrong_action", "verb": "todo"}])
async def test_someone_elses_job_isnt_found_and_teaches_nothing(async_client, test_db, mailbox, plugins, ai, body):
    theirs = await job_from(new_mailbox(), mailbox, "archive_noise", Artifacts(noise_rationale="x"), owner_id="someone-else")

    for job_id in (theirs.id, PydanticObjectId()):
        response = await async_client.post(f"/api/v1/jobs/{job_id}/correct", json=body)
        assert response.status_code == 404

    assert await Rule.find_all().count() == 0 and len(mailbox.messages("INBOX")) == 1


async def test_a_corrected_failed_job_keeps_nothing_of_the_old_action(async_client, test_db, mailbox, plugins):
    due = "2026-12-01T09:00:00Z"
    job = await job_from(new_mailbox(), mailbox, "reply", Artifacts(draft="Yes"), state="failed", error="send failed",
                         reminder="nobody answered", due=due)

    corrected = (await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})).json()

    assert (corrected["state"], corrected["error"], corrected["reminder"], corrected["due"]) == ("done", None, None, None)
    assert (corrected["title"], corrected["evidence"]) == ("Q4 budget", [])  # the mail's subject, not the old action's title


@pytest.mark.parametrize(("verb", "body"), [
    ("archive_noise", {"kind": "not_noise"}),
    ("reply", {"kind": "wrong_action", "verb": "reply"}),
])
async def test_a_failed_job_can_be_corrected_like_an_open_one(async_client, test_db, mailbox, plugins, ai, verb, body):
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb=verb).insert()
    job = await job_from(ana, mailbox, verb, Artifacts(draft="Yes", noise_rationale="x"), state="failed", error="it broke")
    ai.result = Proposal(needs_owner=False, verb="reply", title="Ana asks to meet Thursday at 3pm", evidence=[QUESTION],
                         draft="Thursday at 3 works.", confidence=0.9)

    response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json=body)

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["error"]) == ("open", None)
    assert await rules() == ([] if body["kind"] == "not_noise" else [("sender", ana.address.lower(), "reply")])


async def test_a_sender_rule_that_chose_the_wrong_verb_is_the_one_corrected(async_client, test_db, mailbox, plugins):
    ana = new_mailbox()
    await Rule(owner_id=OWNER_ID, match="sender", value=ana.address, verb="reply").insert()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Yes"))
    await Message.find(Message.id == job.message_ids[0]).update({"$set": {"list_id": "<deals.shop.example>"}})

    await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})

    assert await rules() == [("sender", ana.address.lower(), "archive_noise")]


async def test_a_lesson_that_fails_to_store_still_returns_the_corrected_job(async_client, test_db, mailbox, plugins, caplog):
    ana = new_mailbox()
    job = await job_from(ana, mailbox, "reply", Artifacts(draft="Yes"))
    # A stored rule for the sender that can't be read: learning from the correction fails, as a broken collection does.
    await Rule.get_pymongo_collection().insert_one({"owner_id": OWNER_ID, "match": "sender", "value": ana.address.lower(), "verb": "not a verb"})

    with caplog.at_level(logging.ERROR, logger="app.api.routers.jobs"):
        response = await async_client.post(f"/api/v1/jobs/{job.id}/correct", json={"kind": "noise"})

    assert response.status_code == 200 and response.json()["state"] == "done"
    assert "Couldn't learn from the correction" in caplog.text
