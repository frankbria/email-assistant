"""Finishing jobs and archive-on-done (spec §10.3): a message is archived only when every job that
references it is final (done or dismissed), and only by a verified move. Anything short of that
reopens the job with an error naming the plugin (AC-1.3)."""

import asyncio
from typing import Literal

from beanie import PydanticObjectId
from beanie.operators import In, NotIn
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from app.models.job import Job
from app.models.message import Message
from app.plugins.calls import InvalidCursor, SyncError, call_plugin, refs_in_inbox
from app.plugins.registry import PluginRegistry
from mailbox_contract import MoveResult

Outcome = Literal["done", "dismissed"]
# A message waits for these to be final; handled_elsewhere jobs' mail already left the inbox.
SETTLED = ("done", "dismissed", "handled_elsewhere")


class JobNotOpen(Exception):
    """Only an open job can be finished (it may have been finished or handled elsewhere already)."""


async def finish(job_id: PydanticObjectId, outcome: Outcome, plugins: PluginRegistry) -> Job:
    """Done (the action succeeded, or a todo's owner tapped done) or dismissed; then archive what's settled."""
    # Out of `open` before any archive, so a sync pass can't close it as handled elsewhere meanwhile.
    claimed = await Job.find(Job.id == job_id, Job.state == "open").update({"$set": {"state": outcome, "error": None}})
    if not claimed.modified_count:
        raise JobNotOpen(f"job {job_id} isn't open")
    job = await Job.get(job_id)
    assert job is not None
    try:
        errors = await archive_settled_messages(job, plugins)
    except asyncio.CancelledError:  # a BaseException: interrupted, it must still end retryable
        await asyncio.shield(reopen(job_id, outcome, ["finishing was interrupted, so the message is still in the inbox"]))
        raise
    except Exception as error:  # whatever broke, the job must not stay final while its mail is in the inbox
        errors = [f"archiving failed ({error}), so the message is still in the inbox"]
    if errors:
        await reopen(job_id, outcome, errors)
    refreshed = await Job.get(job_id)
    assert refreshed is not None
    return refreshed


async def reopen(job_id: PydanticObjectId, outcome: Outcome, errors: list[str]) -> None:
    """Back to open with what went wrong, unless something else changed the job meanwhile."""
    await Job.find(Job.id == job_id, Job.state == outcome).update({"$set": {"state": "open", "error": "; ".join(errors)}})


async def archive_settled_messages(job: Job, plugins: PluginRegistry) -> list[str]:
    """Archives each of the job's messages that no other unsettled job needs and that is still in its
    account's inbox. Returns what went wrong, one line per plugin problem.
    shortcut: no per-message claim, so two jobs on one message finished at the same instant can both
    archive (one then reopens); and a multi-message job that fails partway stays reopened with some
    mail archived. Both need a durable per-message archive claim once multi-message jobs exist (#59, #88)."""
    errors = []
    for message in await Message.find(In(Message.id, job.message_ids)).to_list():
        waiting = await Job.find(Job.message_ids == message.id, Job.id != job.id, NotIn(Job.state, SETTLED)).exists()
        if waiting:
            continue  # another job still needs it in the inbox (AC-2.1)
        problem = await archive(message, plugins)
        if problem:
            errors.append(problem)
    return errors


async def archive(message: Message, plugins: PluginRegistry) -> str | None:
    plugin_id = message.plugin_id
    client = plugins.clients.get(plugin_id)
    if client is None:
        return f"{plugin_id} isn't connected, so the message is still in the inbox"
    try:
        if message.ref not in await refs_in_inbox(plugin_id, client, [message.ref]):
            return None  # already out of the inbox (moved elsewhere): nothing to archive
        result = MoveResult.model_validate(await call_plugin(plugin_id, client, "archive", {"ref": message.ref}))
    except ValidationError:
        return f"{plugin_id} couldn't archive the message (it answered outside the contract), so it is still in the inbox"
    except (SyncError, InvalidCursor, TimeoutError, MCPError, OSError) as error:
        return f"{plugin_id} couldn't archive the message ({error}), so it is still in the inbox"
    if not (result.ok and result.verified):
        return f"{plugin_id} couldn't confirm the archive, so the message is still in the inbox"
    return None
