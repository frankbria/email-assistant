"""Finishing jobs and archive-on-done (spec §10.3): a message is archived only when every job that
references it is final (done or dismissed), and only by a verified move. Anything short of that
reopens the job with an error naming the plugin (AC-1.3). Every action is written to the action log here, so
no caller can skip it (spec §9, §10.6)."""

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

from app.models.action_log import Action, ActionLogEntry, Actor
from app.models.job import Job, JobState, PermissionLevel, Verb
from app.models.message import Message
from app.plugins.calls import InvalidCursor, SyncError, call_plugin, refs_in_inbox
from app.plugins.registry import PluginRegistry
from app.unsubscribe import UnsubscribeMail, is_https, unsubscribe_mail, unsubscribe_target
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


class NotUndoable(Exception):
    """The entry can't be undone; the message says why in the owner's words."""


class ArchiveFailed(Exception):
    """The message is still in the inbox; the message names the plugin and why."""


async def record(
    owner_id: str, job_id: PydanticObjectId, action: Action, message_ids: list[PydanticObjectId], by: Actor,
    level: PermissionLevel | None, error: str | None = None, undoable: bool = False,
) -> ActionLogEntry:
    """Writes one action to the history.
    shortcut: written after the action, not in one transaction with it, so a DB failure in between loses the entry;
    use a transaction once MongoDB runs as a replica set."""
    entry = ActionLogEntry(owner_id=owner_id, action=action, job_id=job_id, message_ids=message_ids, by=by,
                           permission_level=level, ok=error is None, error=error, undoable=undoable)
    await entry.insert()
    return entry


async def finish(
    job_id: PydanticObjectId,
    outcome: Outcome,
    plugins: PluginRegistry,
    claim_from: tuple[JobState, ...] = ("open",),
    verb: Verb | None = None,
    *,
    by: Actor,
    level: PermissionLevel | None,
    messages: list[PydanticObjectId] | None = None,
) -> Job:
    """Done (the action succeeded, or a todo's owner tapped done) or dismissed; then archive what's settled.
    `claim_from`: execute() finishes a job it already holds as `sending`. `verb`: only while the job is still
    that verb and not an ask-owner card (the owner approved what they saw, not a choice made meanwhile).
    `messages`: only while the job still covers exactly those (a digest gathers mail; the tap covers what was shown).
    `level`: the permission it ran under, stored on the job once it took effect (None: a dismissal)."""
    unchanged: dict[str, object] = {"verb": verb, "ask_owner": False} if verb else {}
    if messages is not None:
        unchanged["message_ids"] = messages
    # Out of `open` before any archive, so a sync pass can't close it as handled elsewhere meanwhile.
    claimed = await Job.find(Job.id == job_id, In(Job.state, list(claim_from)), unchanged).update({"$set": {"state": outcome, "error": None}})
    if not claimed.modified_count:
        raise JobNotOpen(f"job {job_id} isn't open")
    archived: list[PydanticObjectId] = []
    action: Action = "dismissed" if outcome == "dismissed" else "archived"
    job: Job | None = None
    try:  # everything after the claim: any failure must end with the job reopened, never stuck final
        job = await Job.get(job_id)
        assert job is not None
        errors = await archive_settled_messages(job, plugins, archived)
    except asyncio.CancelledError:  # a BaseException: interrupted, it must still end retryable
        await asyncio.shield(interrupted(job, job_id, outcome, action, archived, by, level))
        raise
    except Exception as error:  # whatever broke, the job must not stay final while its mail is in the inbox
        errors = [f"archiving failed ({error}), so the message is still in the inbox"]
    if errors:
        await reopen(job_id, outcome, errors)
    elif level is not None:
        await Job.find(Job.id == job_id, Job.state == outcome).update({"$set": {"permission_level": level}})
    refreshed = await Job.get(job_id)
    assert refreshed is not None
    if outcome == "done" and not archived:
        action = "done"
    await record(refreshed.owner_id, job_id, action, archived or refreshed.message_ids, by, level, "; ".join(errors) or None, bool(archived))
    return refreshed


async def interrupted(
    job: Job | None, job_id: PydanticObjectId, outcome: Outcome, action: Action, archived: list[PydanticObjectId],
    by: Actor, level: PermissionLevel | None,
) -> None:
    """A finish cut short ends retryable; the copies it already archived left the inbox, so they keep their
    history entry and its undo."""
    problem = "finishing was interrupted, so the message is still in the inbox"
    await reopen(job_id, outcome, [problem])
    if job is not None and archived:
        await record(job.owner_id, job_id, action, archived, by, level, problem, undoable=True)


async def reopen(job_id: PydanticObjectId, outcome: Outcome, errors: list[str]) -> None:
    """Back to open with what went wrong, unless something else changed the job meanwhile."""
    await Job.find(Job.id == job_id, Job.state == outcome).update({"$set": {"state": "open", "error": "; ".join(errors)}})


async def archive_settled_messages(job: Job, plugins: PluginRegistry, archived: list[PydanticObjectId]) -> list[str]:
    """Archives each of the job's messages that no other unsettled job needs and that is still in its
    account's inbox, adding each one moved to `archived`. Returns what went wrong, one line per plugin problem.
    A job that failed partway reopens; its retry archives only what is still in the inbox."""
    errors = []
    for message in await Message.find(In(Message.id, job.message_ids)).to_list():
        waiting = await Job.find(Job.message_ids == message.id, Job.id != job.id, NotIn(Job.state, SETTLED)).exists()
        if waiting:
            continue  # another job still needs it in the inbox (AC-2.1)
        if not await claim_archive(message, job):
            continue  # another final job is archiving it now; if that fails, it reopens and still holds the mail
        try:
            if await archive(message, plugins.clients.get(message.plugin_id)):
                assert message.id is not None
                archived.append(message.id)
        except ArchiveFailed as problem:
            errors.append(str(problem))
        finally:
            await asyncio.shield(Message.find(Message.id == message.id, Message.archive_claim == job.id).update(
                {"$set": {"archive_claim": None}}
            ))
    return errors


async def claim_archive(message: Message, job: Job) -> bool:
    """Two final jobs over one message (finished at the same instant) must not both move it: the first to claim it
    archives it. A job may retake its own claim.
    shortcut: a process dying mid-archive strands its claim (as it strands its job final); expire claims like
    STALE_SENDING if that is ever seen."""
    claimed = await Message.find({"_id": message.id, "archive_claim": {"$in": [None, job.id]}}).update(
        {"$set": {"archive_claim": job.id}}
    )
    return bool(claimed.matched_count)


async def archive(message: Message, client: Client | None) -> bool:
    """Archives one copy if it's still in its inbox: True once moved, False if it already left the inbox.
    Raises ArchiveFailed, naming the plugin, when it couldn't."""
    plugin_id = message.plugin_id
    if client is None:
        raise ArchiveFailed(f"{plugin_id} isn't connected, so the message is still in the inbox")
    try:
        if message.ref not in await refs_in_inbox(plugin_id, client, [message.ref]):
            return False  # already out of the inbox (moved elsewhere): nothing to archive
        result = MoveResult.model_validate(await call_plugin(plugin_id, client, "archive", {"ref": message.ref}))
    except ValidationError as error:
        raise ArchiveFailed(f"{plugin_id} couldn't archive the message (it answered outside the contract), so it is still in the inbox") from error
    except (SyncError, InvalidCursor, TimeoutError, MCPError, OSError) as error:
        raise ArchiveFailed(f"{plugin_id} couldn't archive the message ({error}), so it is still in the inbox") from error
    if not (result.ok and result.verified):
        raise ArchiveFailed(f"{plugin_id} couldn't confirm the archive, so the message is still in the inbox")
    return True


async def restore(message: Message, client: Client | None) -> str | None:
    """Moves one archived copy back to its inbox, verified like archive(); what went wrong, naming the plugin, or None."""
    plugin_id = message.plugin_id
    if client is None:
        return f"{plugin_id} isn't connected, so the message is still archived"
    try:
        if message.ref in await refs_in_inbox(plugin_id, client, [message.ref]):
            return None  # already back (an earlier attempt that half-worked, or the owner moved it)
        result = MoveResult.model_validate(await call_plugin(plugin_id, client, "restore", {"ref": message.ref}))
    except ValidationError:
        return f"{plugin_id} couldn't restore the message (it answered outside the contract), so it is still archived"
    except (SyncError, InvalidCursor, TimeoutError, MCPError, OSError) as error:
        return f"{plugin_id} couldn't restore the message ({error}), so it is still archived"
    if not (result.ok and result.verified):
        return f"{plugin_id} couldn't confirm the restore, so the message is still archived"
    return None


async def undo(entry: ActionLogEntry, plugins: PluginRegistry) -> ActionLogEntry:
    """Spec §9: restore after an archive (or a dismissal that archived); a send can't be unsent and nothing
    else moved mail. The restore is logged as its own entry; a failed one leaves the original undoable."""
    if entry.action == "sent":
        raise NotUndoable("a sent email can't be unsent")
    if not entry.undoable:
        raise NotUndoable("only archived mail can be undone (restored to the inbox)")
    # Claimed first, so two taps can't both restore and log.
    claimed = await ActionLogEntry.find(ActionLogEntry.id == entry.id, {"undone": False}).update({"$set": {"undone": True}})
    if not claimed.modified_count:
        raise NotUndoable("it was already undone")
    errors: list[str] = []
    restored = False
    try:
        for message in await Message.find(In(Message.id, entry.message_ids)).to_list():
            problem = await restore(message, plugins.clients.get(message.plugin_id))
            if problem:
                errors.append(problem)
        restored = not errors
    finally:  # failed, raised or cancelled: the archive stays undoable
        # shortcut: a process dying between the claim and this release strands the entry as undone; make the claim
        # and the restore's entry one transaction once MongoDB runs as a replica set.
        if not restored:
            await asyncio.shield(ActionLogEntry.find(ActionLogEntry.id == entry.id).update({"$set": {"undone": False}}))
    return await record(entry.owner_id, entry.job_id, "restored", entry.message_ids, "owner", None, "; ".join(errors) or None)


async def execute(
    job_id: PydanticObjectId, plugins: PluginRegistry, body: str | None = None, forward_to: str | None = None,
    *, by: Actor, level: PermissionLevel, unsubscribe_request: UnsubscribeMail | None = None,
) -> Job:
    """The owner approved a reply, forward or unsubscribe email: send it from the account that received the mail,
    then finish the job (archive-on-done). A failed send leaves the job `failed` and the mail in the inbox
    (AC-2.2); calling this again retries, and once it was sent a retry only archives. `body` is the
    owner's text (None: the draft); `forward_to` is the recipient the owner confirmed; `unsubscribe_request` is the
    mailto the owner confirmed (see unsubscribe)."""
    job = await Job.get(job_id)
    if job is None or job.verb not in ("reply", "forward", "unsubscribe"):
        raise ValueError(f"only reply, forward and unsubscribe jobs send; job {job_id} isn't one")
    if (unsubscribe_request is not None) != (job.verb == "unsubscribe"):
        # The job became another action while the tap was on its way: send neither what wasn't approved.
        raise ValueError(f"job {job_id} changed since it was approved, look at it again")
    now = datetime.now(UTC)
    # Still the verb read above: another action chosen meanwhile must not be sent as this one.
    claimable = {"_id": job_id, "verb": job.verb, "ask_owner": False, "$or": [
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
        problem = None if job.sent_at else await send(job, plugins, body, forward_to, unsubscribe_request)
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
        await record(job.owner_id, job_id, "sent", job.message_ids, by, level, problem)
        failed = await Job.get(job_id)
        assert failed is not None
        return failed
    # The plugin confirmed the send: record it even if cancelled now, so no retry ever sends it again.
    await asyncio.shield(Job.find(Job.id == job_id).update({"$set": {"sent_at": job.sent_at or now}}))
    # Once per job, and again if a crash lost it after the send: a retry only archives, but fills the history's gap.
    if not await ActionLogEntry.find(ActionLogEntry.job_id == job_id, ActionLogEntry.action == "sent", {"ok": True}).exists():
        await record(job.owner_id, job_id, "sent", job.message_ids, by, level)
    return await finish(job_id, "done", plugins, claim_from=("sending",), by=by, level=level)


async def mark_failed(job_id: PydanticObjectId, problem: str) -> None:
    await Job.find(Job.id == job_id, Job.state == "sending").update({"$set": {"state": "failed", "error": f"send failed — retry: {problem}"}})


def reply_subject(subject: str) -> str:
    return subject if REPLY_PREFIX.match(subject) else f"Re: {subject.strip() or '(no subject)'}"


def forward_subject(subject: str) -> str:
    return subject if FORWARD_PREFIX.match(subject) else f"Fwd: {subject.strip() or '(no subject)'}"


async def send(
    job: Job, plugins: PluginRegistry, body: str | None, forward_to: str | None, unsubscribe_request: UnsubscribeMail | None
) -> str | None:
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
    elif job.verb == "unsubscribe":
        if unsubscribe_request is None:
            return "confirm the unsubscribe target first"
        arguments = {"to": [{"email": unsubscribe_request.address}], "subject": unsubscribe_request.subject,
                     "body_text": unsubscribe_request.body}
    else:
        if not forward_to:  # never the AI's suggestion alone: a forward's recipient is the owner's call (§4)
            return "choose who to forward it to"
        original = MessageDetail.model_validate(await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref}))
        quoted = (f"---------- Forwarded message ---------\nFrom: {original.sender.email}\nDate: {original.date.isoformat()}\n"
                  f"Subject: {original.subject}\n\n{original.text}")
        arguments = {"to": [{"email": forward_to}], "subject": forward_subject(message.subject), "body_text": f"{text}\n\n{quoted}"}
    result = SendResult.model_validate(await call_plugin(message.plugin_id, client, "send", arguments))
    return None if result.ok else f"{message.plugin_id} didn't send it"


async def unsubscribe(job_id: PydanticObjectId, plugins: PluginRegistry, confirmed_target: str | None, *, level: PermissionLevel) -> Job:
    """The owner's tap on an unsubscribe job, so always `by` the owner (spec §4: never_auto). The target is read from
    the mail again and must be the one the owner was shown: an https link was opened by their browser, so the job
    only finishes; a mailto is sent to its one address."""
    target = await unsubscribe_target_of(job_id, plugins)
    if target != confirmed_target:
        raise ValueError("confirm the unsubscribe target this mail names")
    if is_https(target):
        return await finish(job_id, "done", plugins, verb="unsubscribe", by="owner", level=level)
    return await execute(job_id, plugins, by="owner", level=level, unsubscribe_request=unsubscribe_mail(target))


async def unsubscribe_target_of(job_id: PydanticObjectId, plugins: PluginRegistry) -> str:
    """The job's List-Unsubscribe target, read from the mail through its plugin; ValueError says why there's none."""
    job = await Job.get(job_id)
    if job is None or job.verb != "unsubscribe":
        raise ValueError(f"job {job_id} isn't an unsubscribe")
    message = await Message.get(job.message_ids[0])  # any copy: they share the headers
    assert message is not None
    client = plugins.clients.get(message.plugin_id)
    if client is None:
        raise ValueError(f"{message.plugin_id} isn't connected, so the mail can't be read")
    try:
        detail = MessageDetail.model_validate(await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref}))
    except (SyncError, InvalidCursor, TimeoutError, ValidationError, MCPError, OSError) as error:
        raise ValueError(f"{message.plugin_id} couldn't read the mail ({error})") from error
    target = unsubscribe_target(detail.headers)
    if target is None:
        raise ValueError("this mail names no safe way to unsubscribe")
    return target


async def defer(job_id: PydanticObjectId, until: datetime | None = None, *, by: Actor, level: PermissionLevel) -> Job:
    """Hides a snooze or an approved follow-up until its date (`until`, else the date the AI extracted)."""
    job = await Job.get(job_id)
    if job is None or job.verb not in ("snooze", "follow_up"):
        raise ValueError(f"only snooze and follow-up jobs wait for a date; job {job_id} isn't one")
    when = until or job.due
    if when is None:
        raise ValueError(f"job {job_id} needs a date to wait for")
    still = (Job.id == job_id, Job.state == "open", Job.verb == job.verb, Job.ask_owner == False)  # noqa: E712  (a query, not a bool)
    claimed = await Job.find(*still).update({"$set": {"state": "snoozed", "due": when, "reminder": None, "permission_level": level}})
    if not claimed.modified_count:
        raise JobNotOpen(f"job {job_id} isn't open")
    await record(job.owner_id, job_id, "snoozed", job.message_ids, by, level)
    deferred = await Job.get(job_id)
    assert deferred is not None
    return deferred


async def wake_due(owner_id: str, plugins: PluginRegistry, now: datetime, check_follow_ups: bool = True) -> int:
    """Brings back every snoozed job whose date has come: a snooze reopens; a follow-up that got its answer
    is done (archive-on-done), one that didn't reopens with a reminder. Open reminders are re-checked each
    pass, so an answer arriving late (or missed by a sync that failed that pass) resolves them. One broken
    job never stops the rest. `check_follow_ups` is False on a pass whose sent folders didn't sync: the
    owner's latest reply may be missing, so follow-ups wait. Returns how many woke."""
    woken = 0
    due = await Job.find(Job.owner_id == owner_id, Job.state == "snoozed", {"due": {"$lte": now}}).to_list()
    reminded = await Job.find(Job.owner_id == owner_id, Job.state == "open", Job.verb == "follow_up", {"reminder": {"$ne": None}}).to_list()
    if not check_follow_ups:
        due, reminded = [job for job in due if job.verb != "follow_up"], []
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
        await finish(job.id, "done", plugins, claim_from=(job.state,), verb=job.verb, by="app", level=job.permission_level)
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
    correspondent = original.sender.email
    to_them = {"$regex": f"^{re.escape(correspondent)}$", "$options": "i"}
    # The owner's turns: threaded to the original, or later mail to the correspondent (a reply to their answer
    # threads to the answer, not the original).
    replies = await Message.find(
        Message.owner_id == job.owner_id, Message.folder == "sent",
        {"$or": [{"in_reply_to": original.message_id}, {"to.email": to_them, "date": {"$gte": original.date}}]},
    ).to_list()
    since = max([original.date, *(reply.date for reply in replies)])
    answered = await Message.find(
        Message.owner_id == job.owner_id, Message.folder == "inbox", Message.id != original.id,
        {"date": {"$gt": since}},  # after the owner's latest reply: an earlier exchange doesn't count
        {"$or": [
            {"in_reply_to": {"$in": [reply.message_id for reply in replies if reply.message_id]}},
            {"sender.email": to_them},
        ]},
    ).exists()
    return None if answered else f"No answer from {correspondent} to “{original.subject}” since {since:%Y-%m-%d}"

