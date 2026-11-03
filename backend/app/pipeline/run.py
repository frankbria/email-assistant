"""Pipeline orchestration (spec §8): each new inbox message goes minimize → rules → AI proposal →
validate, and becomes a job or an ask-owner job. Anything that goes wrong asks the owner; the
optional monthly AI cap (§5.3) does too, with one warning per month."""

import logging
from datetime import UTC, datetime

from mcp import Client
from pydantic import ValidationError

from beanie.operators import In
from pymongo import ReturnDocument

from app.executor import archive, reopen
from app.models.ai_usage import AiUsage
from app.models.job import Job
from app.models.message import Message
from app.pipeline.minimize import minimize
from app.pipeline.propose import forward_candidates, propose
from app.pipeline.rules import apply_rule, matching_rule
from app.pipeline.validate import ask_owner_job, to_job
from app.plugins.calls import call_plugin, refs_in_inbox
from app.services.ai_provider import AIProposalError, AIProvider
from mailbox_contract import MessageDetail

logger = logging.getLogger(__name__)


async def process_pending(owner_id: str, plugin_id: str, client: Client, provider: AIProvider, cap: int | None) -> int:
    """Every inbox message of this plugin still without its job, oldest first, including any a crash
    left behind. Returns how many were processed; one failure doesn't stop the rest."""
    pending = Message.find(
        Message.owner_id == owner_id, Message.plugin_id == plugin_id, Message.folder == "inbox",
        {"pipeline_done": {"$ne": True}},  # also documents stored before the field existed
    )
    messages = await pending.sort("date").to_list()
    # Mail handled elsewhere while it waited (e.g. through an AI outage) needs no job and no AI call.
    present = await refs_in_inbox(plugin_id, client, [message.ref for message in messages]) if messages else set()
    processed = 0
    for message in messages:
        if message.ref not in present:
            message.pipeline_done = True
            await message.save()
            continue
        try:
            await process(message, client, provider, cap)
            processed += 1
        except Exception:  # e.g. MongoDB briefly unreachable: the message stays pending for next pass
            logger.exception("Pipeline failed for message %s of plugin %s; retrying next pass", message.id, plugin_id)
    return processed


async def process(message: Message, client: Client, provider: AIProvider, cap: int | None) -> Job:
    """The message's job, made once. Transient failures (plugin or AI down) raise and leave it pending."""
    assert message.id is not None, "only stored messages are processed"
    job = await Job.find_one(Job.owner_id == message.owner_id, Job.message_ids == message.id)
    if job is None and (sibling := await sibling_job(message)) is not None:
        job = await attach_copy(sibling, message)
    if job is None:
        job = await decide(message, client, provider, cap)
        job.requires_approval = message.first_pass
        await job.insert()
    elif job.state in ("done", "dismissed"):
        await archive_late_copy(job, message, client)
    message.pipeline_done = True
    await message.save()
    return job


async def sibling_job(message: Message) -> Job | None:
    """The job over another copy of this mail (same Message-ID, another account or ref), if any.
    A blank Message-ID identifies nothing; a copy handled elsewhere left its inbox, so it doesn't count."""
    if not message.message_id:
        return None
    copies = await Message.find(
        Message.owner_id == message.owner_id, Message.message_id == message.message_id, Message.id != message.id
    ).to_list()
    if not copies:
        return None
    return await Job.find_one(
        Job.owner_id == message.owner_id, In(Job.message_ids, [copy.id for copy in copies]), Job.state != "handled_elsewhere"
    )


async def attach_copy(job: Job, message: Message) -> Job:
    """One job for every copy (spec §5.3). Returns the job as stored right after attaching, so a
    finish that landed meanwhile is seen (its archive may have missed this copy)."""
    stored = await Job.get_pymongo_collection().find_one_and_update(
        {"_id": job.id}, {"$addToSet": {"message_ids": message.id}}, return_document=ReturnDocument.AFTER
    )
    assert stored is not None
    return Job.model_validate(stored)


async def archive_late_copy(job: Job, message: Message, client: Client) -> None:
    """A copy that joined a finished job is archived like the rest were (a no-op once it's out of the
    inbox, so a crash here is retried safely); if that fails, the job reopens with the error."""
    problem = await archive(message, client)
    if problem and job.id is not None and job.state in ("done", "dismissed"):
        await reopen(job.id, "done" if job.state == "done" else "dismissed", [problem])


async def decide(message: Message, client: Client, provider: AIProvider, cap: int | None) -> Job:
    answer = await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref})
    try:
        text = MessageDetail.model_validate(answer).text
    except ValidationError as error:
        return ask_owner_job(message, [f"couldn't read the message: {error.error_count()} invalid fields"], [])
    rule = await matching_rule(message.owner_id, message)
    suggested = [rule.verb] if rule else []
    if not await take_ai_call(cap):
        return ask_owner_job(message, ["the monthly AI cap is reached"], suggested)
    try:
        proposal = await propose(message, text, provider, fixed_verb=rule.verb if rule else None)
    except AIProposalError:
        return ask_owner_job(message, ["the AI gave no usable proposal"], suggested)
    except Exception:  # an outage or a failed local read isn't a used call; the message waits for the next pass
        await refund_ai_call()
        raise
    return to_job(message, apply_rule(proposal, rule), minimize(text, message.subject), await forward_candidates(message.owner_id))


async def refund_ai_call() -> None:
    month = datetime.now(UTC).strftime("%Y-%m")
    await AiUsage.get_pymongo_collection().update_one({"month": month, "calls": {"$gt": 0}}, {"$inc": {"calls": -1}})


async def take_ai_call(cap: int | None) -> bool:
    """Counts one AI call this month, unless that would pass the cap. The first refusal of a month
    records the month's one warning."""
    month = datetime.now(UTC).strftime("%Y-%m")
    usage = AiUsage.get_pymongo_collection()
    await usage.update_one({"month": month}, {"$setOnInsert": {"calls": 0, "cap_warned_at": None}}, upsert=True)
    within_cap = {"month": month} if cap is None else {"month": month, "calls": {"$lt": cap}}
    counted = await usage.update_one(within_cap, {"$inc": {"calls": 1}})
    if counted.modified_count:
        return True
    first_refusal = await usage.update_one({"month": month, "cap_warned_at": None}, {"$set": {"cap_warned_at": datetime.now(UTC)}})
    if first_refusal.modified_count:
        logger.warning("The monthly AI cap of %d calls is reached; new mail goes to the owner until next month", cap)
    return False
