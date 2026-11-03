"""Pipeline orchestration (spec §8): each new inbox message goes minimize → rules → AI proposal →
validate, and becomes a job or an ask-owner job. Anything that goes wrong asks the owner; the
optional monthly AI cap (§5.3) does too, with one warning per month."""

import logging
from datetime import UTC, datetime

from mcp import Client
from pydantic import ValidationError

from app.models.ai_usage import AiUsage
from app.models.job import Job
from app.models.message import Message
from app.pipeline.minimize import minimize
from app.pipeline.propose import forward_candidates, propose
from app.pipeline.rules import apply_rule, matching_rule
from app.pipeline.validate import ask_owner_job, to_job
from app.plugins.calls import InvalidCursor, SyncError, call_plugin
from app.services.ai_provider import AIProposalError, AIProvider
from mailbox_contract import MessageDetail

logger = logging.getLogger(__name__)


async def process_pending(owner_id: str, plugin_id: str, client: Client, provider: AIProvider, cap: int | None) -> int:
    """Every inbox message of this plugin still without its job, oldest first, including any a crash
    left behind. Returns how many were processed; one failure doesn't stop the rest."""
    pending = Message.find(
        Message.owner_id == owner_id, Message.plugin_id == plugin_id, Message.folder == "inbox", {"pipeline_done": False}
    )
    processed = 0
    for message in await pending.sort("date").to_list():
        try:
            await process(message, client, provider, cap)
            processed += 1
        except Exception:  # e.g. MongoDB briefly unreachable: the message stays pending for next pass
            logger.exception("Pipeline failed for message %s of plugin %s; retrying next pass", message.id, plugin_id)
    return processed


async def process(message: Message, client: Client, provider: AIProvider, cap: int | None) -> Job:
    assert message.id is not None, "only stored messages are processed"
    existing = await Job.find_one(Job.owner_id == message.owner_id, Job.message_ids == message.id)
    job = existing or await decide(message, client, provider, cap)
    if existing is None:
        await job.insert()
    message.pipeline_done = True
    await message.save()
    return job


async def decide(message: Message, client: Client, provider: AIProvider, cap: int | None) -> Job:
    try:
        answer = await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref})
        text = MessageDetail.model_validate(answer).text
    except (SyncError, InvalidCursor, TimeoutError, ValidationError) as error:
        return ask_owner_job(message, [f"couldn't read the message: {error}"], [])
    rule = await matching_rule(message.owner_id, message)
    if not await take_ai_call(cap):
        return ask_owner_job(message, ["the monthly AI cap is reached"], [rule.verb] if rule else [])
    try:
        proposal = await propose(message, text, provider, fixed_verb=rule.verb if rule else None)
    except AIProposalError:
        return ask_owner_job(message, ["the AI gave no usable proposal"], [rule.verb] if rule else [])
    return to_job(message, apply_rule(proposal, rule), minimize(text, message.subject), await forward_candidates(message.owner_id))


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
