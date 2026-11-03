# Pipeline orchestration (spec §8, §5.3 AI spend cap): new inbox mail flows from sync to a job or an
# ask-owner job. Reference IMAP plugin on GreenMail, real MongoDB; the AI is the repo's FakeAIProvider.
import logging

import pytest

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


async def test_a_message_the_plugin_can_no_longer_read_goes_to_the_owner(test_db, mailbox: Mailbox):
    await add_owner(test_db)
    await Message.model_validate({
        "owner_id": OWNER, "plugin_id": "reference-imap", "ref": "<gone@x>", "message_id": "<gone@x>",
        "sender": {"email": "a@example.com"}, "to": [], "cc": [], "date": "2026-11-02T12:00:00Z",
        "subject": "Vanished", "snippet": "",
    }).insert()

    await run_pass(test_db, mailbox, FakeAIProvider(result=meeting()))

    [job] = await jobs()
    assert job.ask_owner and job.problems[0].startswith("couldn't read the message")


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
