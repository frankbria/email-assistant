"""Finishing jobs and archive-on-done (spec §10.3): a message is archived only when every job that
references it is final (done or dismissed), and only by a verified move. Anything short of that
reopens the job with an error naming the plugin (AC-1.3)."""

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from beanie import PydanticObjectId
from beanie.operators import In, NotIn
from mcp import Client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError
from pymongo import ReturnDocument

from app.models.job import Job, JobState
from app.models.message import Message
from app.plugins.calls import InvalidCursor, SyncError, call_plugin, refs_in_inbox
from app.plugins.registry import PluginRegistry
from mailbox_contract import MessageDetail, MoveResult, SendResult

logger = logging.getLogger(__name__)

Outcome = Literal["done", "dismissed"]
STALE_SENDING = timedelta(minutes=10)  # far past any plugin timeout: the process that claimed it died
REPLY_PREFIX = re.compile(r"^\s*re\s*:", re.IGNORECASE)
FORWARD_PREFIX = re.compile(r"^\s*(?:fw|fwd)\s*:", re.IGNORECASE)
# A message waits for these to be final; handled_elsewhere jobs' mail already left the inbox.
SETTLED = ("done", "dismissed", "handled_elsewhere")


class JobNotOpen(Exception):
    """Only an open job can be finished (it may have been finished or handled elsewhere already)."""


async def finish(
    job_id: PydanticObjectId, outcome: Outcome, plugins: PluginRegistry, claim_from: tuple[JobState, ...] = ("open",)
) -> Job:
    """Done (the action succeeded, or a todo's owner tapped done) or dismissed; then archive what's settled.
    `claim_from`: execute() finishes a job it already holds as `sending`."""
    # Out of `open` before any archive, so a sync pass can't close it as handled elsewhere meanwhile.
    claimed = await Job.find(Job.id == job_id, In(Job.state, list(claim_from))).update({"$set": {"state": outcome, "error": None}})
    if not claimed.modified_count:
        raise JobNotOpen(f"job {job_id} isn't open")
    try:  # everything after the claim: any failure must end with the job reopened, never stuck final
        job = await Job.get(job_id)
        assert job is not None
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
        problem = await archive(message, plugins.clients.get(message.plugin_id))
        if problem:
            errors.append(problem)
    return errors


async def archive(message: Message, client: Client | None) -> str | None:
    """Archives one copy if it's still in its inbox; what went wrong, naming the plugin, or None."""
    plugin_id = message.plugin_id
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


async def execute(
    job_id: PydanticObjectId, plugins: PluginRegistry, body: str | None = None, forward_to: str | None = None
) -> Job:
    """The owner approved a reply or forward: send it from the account that received the mail, then
    finish the job (archive-on-done). A failed send leaves the job `failed` and the mail in the inbox
    (AC-2.2); calling this again retries, and once it was sent a retry only archives. `body` is the
    owner's text (None: the draft); `forward_to` is the recipient the owner confirmed."""
    job = await Job.get(job_id)
    if job is None or job.verb not in ("reply", "forward"):
        raise ValueError(f"only reply and forward jobs send; job {job_id} isn't one")
    now = datetime.now(UTC)
    claimable = {"_id": job_id, "$or": [
        {"state": {"$in": ["open", "failed"]}},
        {"state": "sending", "sending_since": {"$lt": now - STALE_SENDING}},
    ]}
    # Out of open/failed first, so a sync pass can't close it as handled elsewhere mid-send.
    claimed = await Job.get_pymongo_collection().find_one_and_update(
        claimable, {"$set": {"state": "sending", "sending_since": now, "error": None}}, return_document=ReturnDocument.AFTER
    )
    if claimed is None:
        raise JobNotOpen(f"job {job_id} isn't open or failed")
    job = Job.model_validate(claimed)  # as of the claim: an overlapping approval may have sent it meanwhile
    try:
        problem = None if job.sent_at else await send(job, plugins, body, forward_to)
    except asyncio.CancelledError:  # a BaseException: interrupted, it must still end retryable
        await asyncio.shield(mark_failed(job_id, "interrupted before it finished"))
        raise
    except (SyncError, InvalidCursor, TimeoutError, ValidationError, MCPError, OSError) as error:  # the plugin's answer
        problem = str(error) or type(error).__name__
    except Exception as error:  # a bug: still never stuck sending, but logged with its traceback
        logger.exception("Sending job %s failed", job_id)
        problem = str(error) or type(error).__name__
    if problem is not None:
        # shortcut: a send that succeeded but whose answer was lost (timeout) counts as failed and can go
        # twice on retry; fix with an idempotency key once the contract's send takes one.
        await mark_failed(job_id, problem)
        failed = await Job.get(job_id)
        assert failed is not None
        return failed
    # The plugin confirmed the send: record it even if cancelled now, so no retry ever sends it again.
    await asyncio.shield(Job.find(Job.id == job_id).update({"$set": {"sent_at": job.sent_at or now}}))
    return await finish(job_id, "done", plugins, claim_from=("sending",))


async def mark_failed(job_id: PydanticObjectId, problem: str) -> None:
    await Job.find(Job.id == job_id, Job.state == "sending").update({"$set": {"state": "failed", "error": f"send failed — retry: {problem}"}})


def reply_subject(subject: str) -> str:
    return subject if REPLY_PREFIX.match(subject) else f"Re: {subject.strip() or '(no subject)'}"


def forward_subject(subject: str) -> str:
    return subject if FORWARD_PREFIX.match(subject) else f"Fwd: {subject.strip() or '(no subject)'}"


async def send(job: Job, plugins: PluginRegistry, body: str | None, forward_to: str | None) -> str | None:
    """Sends the job's message; what went wrong, or None."""
    message = await Message.get(job.message_ids[0])  # any copy: they share the sender and the content
    assert message is not None
    client = plugins.clients.get(message.plugin_id)
    if client is None:
        return f"{message.plugin_id} isn't connected"
    text = body if body is not None else (job.artifacts.draft or "")
    if job.verb == "reply":
        if not text.strip():
            return "write the reply first"
        arguments: dict[str, object] = {"to": [{"email": message.sender.email}], "subject": reply_subject(message.subject),
                                        "body_text": text, "in_reply_to_ref": message.ref}
    else:
        if not forward_to:  # never the AI's suggestion alone: a forward's recipient is the owner's call (§4)
            return "choose who to forward it to"
        original = MessageDetail.model_validate(await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref}))
        quoted = (f"---------- Forwarded message ---------\nFrom: {original.sender.email}\nDate: {original.date.isoformat()}\n"
                  f"Subject: {original.subject}\n\n{original.text}")
        arguments = {"to": [{"email": forward_to}], "subject": forward_subject(message.subject), "body_text": f"{text}\n\n{quoted}"}
    result = SendResult.model_validate(await call_plugin(message.plugin_id, client, "send", arguments))
    return None if result.ok else f"{message.plugin_id} didn't send it"


async def defer(job_id: PydanticObjectId, until: datetime | None = None) -> Job:
    """Hides a snooze or an approved follow-up until its date (`until`, else the date the AI extracted)."""
    job = await Job.get(job_id)
    if job is None or job.verb not in ("snooze", "follow_up"):
        raise ValueError(f"only snooze and follow-up jobs wait for a date; job {job_id} isn't one")
    when = until or job.due
    if when is None:
        raise ValueError(f"job {job_id} needs a date to wait for")
    claimed = await Job.find(Job.id == job_id, Job.state == "open").update({"$set": {"state": "snoozed", "due": when, "reminder": None}})
    if not claimed.modified_count:
        raise JobNotOpen(f"job {job_id} isn't open")
    deferred = await Job.get(job_id)
    assert deferred is not None
    return deferred


async def wake_due(owner_id: str, plugins: PluginRegistry, now: datetime) -> int:
    """Brings back every snoozed job whose date has come: a snooze reopens; a follow-up that got its answer
    is done (archive-on-done), one that didn't reopens with a reminder. Open reminders are re-checked each
    pass, so an answer arriving late (or missed by a sync that failed that pass) resolves them. One broken
    job never stops the rest. Returns how many woke."""
    woken = 0
    due = await Job.find(Job.owner_id == owner_id, Job.state == "snoozed", {"due": {"$lte": now}}).to_list()
    reminded = await Job.find(Job.owner_id == owner_id, Job.state == "open", Job.verb == "follow_up", {"reminder": {"$ne": None}}).to_list()
    for job in [*due, *reminded]:
        try:
            woken += await wake(job, plugins)
        except JobNotOpen:
            pass  # the owner acted on it meanwhile
        except Exception:  # e.g. its message is gone: log it and keep waking the others
            logger.exception("Waking job %s failed; retrying next pass", job.id)
    return woken


async def wake(job: Job, plugins: PluginRegistry) -> int:
    assert job.id is not None
    reminder = await missing_answer(job) if job.verb == "follow_up" else None
    if job.verb == "follow_up" and reminder is None:  # answered: done, straight from where it waits
        await finish(job.id, "done", plugins, claim_from=(job.state,))
        return 1
    if job.state == "open":
        return 0  # a reminder still without an answer: it stays as it is
    claimed = await Job.find(Job.id == job.id, Job.state == "snoozed").update({"$set": {"state": "open", "reminder": reminder}})
    return claimed.modified_count


async def missing_answer(job: Job) -> str | None:
    """The reminder to show when nobody answered; None when the correspondent answered the owner's reply
    (threaded, or any newer mail from them). The owner's reply is found in the synced sent folder, so replies sent
    outside the app count."""
    original = await Message.get(job.message_ids[0])
    assert original is not None
    replies = await Message.find(
        Message.owner_id == job.owner_id, Message.folder == "sent", Message.in_reply_to == original.message_id
    ).to_list()
    since = max([original.date, *(reply.date for reply in replies)])
    correspondent = original.sender.email
    answered = await Message.find(
        Message.owner_id == job.owner_id, Message.folder == "inbox", Message.id != original.id,
        {"date": {"$gt": since}},  # after the owner's latest reply: an earlier exchange doesn't count
        {"$or": [
            {"in_reply_to": {"$in": [reply.message_id for reply in replies if reply.message_id]}},
            {"sender.email": {"$regex": f"^{re.escape(correspondent)}$", "$options": "i"}},
        ]},
    ).exists()
    return None if answered else f"No answer from {correspondent} to “{original.subject}” since {since:%Y-%m-%d}"

