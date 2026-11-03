# Pipeline orchestration (spec §8, §5.3 AI spend cap): new inbox mail flows from sync to a job or an
# ask-owner job. Reference IMAP plugin on GreenMail, real MongoDB; the AI is the repo's FakeAIProvider.
import logging

import httpx

import pytest
from anthropic import APIConnectionError

from app.models.ai_usage import AiUsage
from app.models.job import Job
from app.models.message import Message
from app.models.rule import Rule
from app.pipeline.proposal import Proposal
from app.services.ai_provider import AIProposalError
from app.sync import SyncEngine
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import OWNER, add_owner, connected
from tests.utils.fakes import FakeAIProvider
from tests.utils.mail_server import Mailbox

pytestmark = pytest.mark.usefixtures("mail_server")
BODY = "Could we meet Thursday at 3pm to go over the Q4 budget?"


def meeting() -> Proposal:
    return Proposal(
        needs_owner=False, verb="reply", title="Ana asks to meet Thursday about the Q4 budget",
        evidence=["Could we meet Thursday at 3pm"], options=["Yes", "No", "Later"], confidence=0.9,
    )


async def stored_message(ref: str) -> Message:
    message = Message.model_validate({
        "owner_id": OWNER, "plugin_id": "reference-imap", "ref": ref, "message_id": ref,
        "sender": {"email": "a@example.com"}, "to": [], "cc": [], "date": "2026-11-02T12:00:00Z",
        "subject": "Vanished", "snippet": "",
    })
    await message.insert()
    return message


async def jobs() -> list[Job]:
    return await Job.find(Job.owner_id == OWNER).sort("created_at").to_list()


async def run_pass(test_db, mailbox: Mailbox, provider: FakeAIProvider, cap: int | None = None) -> None:
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60, provider=provider, ai_monthly_cap=cap).sync_all()


async def test_a_new_message_flows_end_to_end_to_a_job(test_db, mailbox: Mailbox):
    """AC, first half; the second pass shows a processed message never gets a second job."""
    await add_owner(test_db)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    provider = FakeAIProvider(result=meeting())

    await run_pass(test_db, mailbox, provider)
    await run_pass(test_db, mailbox, provider)

    [job] = await jobs()
    assert (job.verb, job.ask_owner, job.title) == ("reply", False, meeting().title)
    assert job.artifacts.options == ["Yes", "No", "Later"]
    [message] = await Message.find(Message.owner_id == OWNER).to_list()
    assert job.message_ids == [message.id] and message.pipeline_done
    assert len(provider.prompts) == 1 and BODY in provider.prompts[0]  # the body came from get_message


async def test_with_the_cap_at_zero_mail_goes_to_the_owner_and_one_warning_is_recorded(test_db, mailbox: Mailbox, caplog):
    """AC, second half: no AI call is made, every message becomes ask-owner, and the warning appears once."""
    await add_owner(test_db)
    for n in range(2):
        mailbox.deliver(sender="ana@example.com", subject=f"Budget {n}", body=BODY)
    provider = FakeAIProvider(result=meeting())

    with caplog.at_level(logging.WARNING, logger="app.pipeline.run"):
        await run_pass(test_db, mailbox, provider, cap=0)

    assert provider.prompts == []
    assert [(job.ask_owner, job.problems) for job in await jobs()] == [(True, ["the monthly AI cap is reached"])] * 2
    assert [record.getMessage() for record in caplog.records].count(
        "The monthly AI cap of 0 calls is reached; new mail goes to the owner until next month"
    ) == 1
    [usage] = await AiUsage.find_all().to_list()
    assert usage.cap_warned_at is not None


async def test_the_cap_counts_ai_calls_across_passes(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    provider = FakeAIProvider(result=meeting())
    for n in range(3):
        mailbox.deliver(sender="ana@example.com", subject=f"Budget {n}", body=BODY)
        await run_pass(test_db, mailbox, provider, cap=2)

    assert [job.ask_owner for job in await jobs()] == [False, False, True]
    assert len(provider.prompts) == 2


async def test_a_stored_rule_decides_the_verb(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    await Rule(owner_id=OWNER, match="sender", value="ana@example.com", verb="snooze").insert()
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    snooze = meeting().model_copy(update={"verb": "snooze", "options": [], "due": "2026-11-05T09:00:00Z"})

    provider = FakeAIProvider(result=snooze)
    await run_pass(test_db, mailbox, provider)

    [job] = await jobs()
    assert (job.verb, job.ask_owner) == ("snooze", False)
    assert "already decided: snooze" in provider.prompts[0]


async def test_when_the_ai_fails_the_owner_is_asked(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)

    await run_pass(test_db, mailbox, FakeAIProvider(error=AIProposalError("refused")))

    [job] = await jobs()
    assert (job.ask_owner, job.problems, job.title) == (True, ["the AI gave no usable proposal"], "Q4 budget")


async def test_a_message_gone_from_the_mailbox_is_done_without_a_job(test_db, mailbox: Mailbox):
    """The plugin says not_found: it left the mailbox before its turn, so there's nothing to do."""
    await add_owner(test_db)
    await stored_message("<gone@x>")

    await run_pass(test_db, mailbox, FakeAIProvider(result=meeting()))

    assert await jobs() == []
    assert [message.pipeline_done for message in await Message.find_all().to_list()] == [True]


async def test_a_message_stored_before_the_pipeline_existed_is_processed(test_db, mailbox: Mailbox):
    """Documents from before this field existed lack pipeline_done entirely."""
    await add_owner(test_db)
    ref = mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()  # sync only, no pipeline
    await Message.find_all().update({"$unset": {"pipeline_done": ""}})

    await run_pass(test_db, mailbox, FakeAIProvider(result=meeting()))

    [job] = await jobs()
    assert not job.ask_owner and ref


async def test_an_ai_outage_costs_nothing_and_the_message_waits_for_the_next_pass(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    outage = APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    await run_pass(test_db, mailbox, FakeAIProvider(error=outage), cap=5)

    assert await jobs() == []
    assert [message.pipeline_done for message in await Message.find_all().to_list()] == [False]
    assert [usage.calls for usage in await AiUsage.find_all().to_list()] == [0]
    await run_pass(test_db, mailbox, FakeAIProvider(result=meeting()), cap=5)
    assert [job.ask_owner for job in await jobs()] == [False]


async def test_first_connect_mail_becomes_a_job_that_needs_the_owners_approval(test_db, mailbox: Mailbox):
    """Spec §5.3: every first-pass decision is `ask`, even for verbs set to autonomous."""
    await add_owner(test_db)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    provider = FakeAIProvider(result=meeting())
    await run_pass(test_db, mailbox, provider)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget again", body=BODY)
    await run_pass(test_db, mailbox, provider)

    assert [(job.ask_owner, job.requires_approval) for job in await jobs()] == [(False, True), (False, False)]


async def test_a_crash_after_the_job_was_stored_never_makes_a_second_job(test_db, mailbox: Mailbox):
    """The job is stored before the message is marked done; a crash in between re-offers the message."""
    await add_owner(test_db)
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    provider = FakeAIProvider(result=meeting())
    await run_pass(test_db, mailbox, provider)
    await Message.find_all().update({"$set": {"pipeline_done": False}})  # as if it crashed before marking

    await run_pass(test_db, mailbox, provider)

    assert len(await jobs()) == 1 and len(provider.prompts) == 1
    assert all(message.pipeline_done for message in await Message.find_all().to_list())


async def test_sent_mail_is_synced_before_proposals_so_they_have_the_owners_voice(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    mailbox.append("Sent", sender=mailbox.address, to="ana@example.com", subject="Re: Offsite", body="Hey Ana! Works for me. Cheers, F")
    mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    provider = FakeAIProvider(result=meeting())

    await run_pass(test_db, mailbox, provider)

    assert "Hey Ana! Works for me. Cheers, F" in provider.prompts[0]


async def test_pending_mail_handled_elsewhere_in_the_meantime_costs_nothing(test_db, mailbox: Mailbox):
    """Archived on a phone while it waited (e.g. through an AI outage): no AI call, no job."""
    await add_owner(test_db)
    ref = mailbox.deliver(sender="ana@example.com", subject="Q4 budget", body=BODY)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        await SyncEngine(registry, test_db["user"], poll_seconds=60).sync_all()  # stored, not yet processed
    mailbox.move(ref, "Archive")
    provider = FakeAIProvider(result=meeting())

    await run_pass(test_db, mailbox, provider)

    assert await jobs() == [] and provider.prompts == []
    assert [message.pipeline_done for message in await Message.find_all().to_list()] == [True]
