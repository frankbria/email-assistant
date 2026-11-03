# backend/app/api/routers/jobs.py
"""The job queue (spec §10.1, §10.2): the owner's open jobs, and what the owner does with one: approve it
(the executor acts), edit its artifacts, choose another action (a fresh proposal for that verb), or dismiss it."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import OwnerId
from app.config import Settings, get_settings
from app.executor import STALE_SENDING, JobNotOpen, defer, execute, finish
from app.models.job import Job, PermissionLevel, Verb
from app.models.message import Message
from app.permissions import level_for, record_approval
from app.pipeline.run import decide
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import AIProvider, get_ai_provider
from mailbox_contract import Address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

IN_QUEUE = ["open", "failed"]  # a failed send waits for the owner to retry or dismiss it


def plugin_registry(request: Request) -> PluginRegistry:
    registry: PluginRegistry = request.app.state.plugins
    return registry


class JobCard(BaseModel):
    job: Job
    sender: Address
    subject: str


class JobEdit(BaseModel):
    """The owner's changes to a job's artifacts; only the fields sent change."""

    draft: str | None = None
    forward_to: str | None = None
    options: list[str] = Field(default_factory=list)
    link: str | None = None
    due: datetime | None = None


class Approval(BaseModel):
    forward_to: str | None = None  # a forward's recipient as the owner confirmed it (never the AI's suggestion alone)


class Choice(BaseModel):
    verb: Verb


async def owned(job_id: PydanticObjectId, owner_id: str) -> Job:
    job = await Job.find_one(Job.id == job_id, Job.owner_id == owner_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def acting(action: Callable[[], Awaitable[Job]]) -> Job:
    """Runs an executor transition; its refusals become the owner's plain-words answer."""
    try:
        return await action()
    except JobNotOpen as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    except ValueError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused


@router.get("", response_model=list[JobCard])
async def list_jobs(owner_id: OwnerId) -> list[JobCard]:
    # A send whose claim went stale (the process died mid-send) waits for the owner's retry like a failed one.
    stuck = {"state": "sending", "sending_since": {"$lt": datetime.now(UTC) - STALE_SENDING}}
    waiting = {"owner_id": owner_id, "$or": [{"state": {"$in": IN_QUEUE}}, stuck]}
    jobs = await Job.find(waiting).sort("-created_at").to_list()
    messages = await Message.find(In(Message.id, [job.message_ids[0] for job in jobs])).to_list()
    by_id = {message.id: message for message in messages}
    return [
        JobCard(job=job, sender=by_id[job.message_ids[0]].sender, subject=by_id[job.message_ids[0]].subject)
        for job in jobs
        if job.message_ids[0] in by_id
    ]


@router.patch("/{job_id}", response_model=Job)
async def edit_job(job_id: PydanticObjectId, edit: JobEdit, owner_id: OwnerId) -> Job:
    await owned(job_id, owner_id)
    sent = edit.model_dump(exclude_unset=True)
    if not sent:
        raise HTTPException(status_code=422, detail="nothing to change")
    changes: dict[str, object] = {"due" if field == "due" else f"artifacts.{field}": value for field, value in sent.items()}
    changes["edited"] = True
    edited = await Job.find(Job.id == job_id, In(Job.state, IN_QUEUE)).update({"$set": changes})
    if not edited.modified_count:
        raise HTTPException(status_code=409, detail=f"job {job_id} isn't open")
    return await owned(job_id, owner_id)


@router.post("/{job_id}/approve", response_model=Job)
async def approve_job(
    job_id: PydanticObjectId, approval: Approval, owner_id: OwnerId, plugins: PluginRegistry = Depends(plugin_registry)
) -> Job:
    job = await owned(job_id, owner_id)
    if job.ask_owner:
        raise HTTPException(status_code=409, detail="choose an action for this mail first")
    if job.verb == "unsubscribe":
        # shortcut: no unsubscribe action yet; approving it acts once the List-Unsubscribe executor lands (#90).
        raise HTTPException(status_code=422, detail="unsubscribing isn't available yet")
    actions: dict[str, Callable[[], Awaitable[Job]]] = {
        "reply": lambda: execute(job_id, plugins, forward_to=approval.forward_to),
        "forward": lambda: execute(job_id, plugins, forward_to=approval.forward_to),
        "snooze": lambda: defer(job_id),
        "follow_up": lambda: defer(job_id),
    }
    acted = await acting(actions.get(job.verb, lambda: finish(job_id, "done", plugins, verb=job.verb)))
    if acted.state in ("done", "snoozed"):
        # The owner's tap is the `ask` path whatever the verb's level; never_auto verbs say so.
        # shortcut: a DB failure after the action and before these writes loses this one streak tick and label (the job
        # is final, so a retry gets 409); make them part of the executor's claim if history (#78) needs them exact.
        level: PermissionLevel = "never_auto" if await level_for(owner_id, job.verb) == "never_auto" else "ask"
        await Job.find(Job.id == job_id, Job.state == acted.state).update({"$set": {"permission_level": level}})
        await record_approval(owner_id, job.verb, edited=acted.edited)
    return await owned(job_id, owner_id)


@router.post("/{job_id}/choose", response_model=Job)
async def choose_action(
    job_id: PydanticObjectId,
    choice: Choice,
    owner_id: OwnerId,
    plugins: PluginRegistry = Depends(plugin_registry),
    provider: AIProvider = Depends(get_ai_provider),
    settings: Settings = Depends(get_settings),
) -> Job:
    job = await owned(job_id, owner_id)
    if job.state != "open" or job.sent_at is not None:
        raise HTTPException(status_code=409, detail=f"job {job_id} isn't open")
    message = await Message.get(job.message_ids[0])
    assert message is not None, "a job's messages are stored before it"
    client = plugins.clients.get(message.plugin_id)
    if client is None:
        raise HTTPException(status_code=409, detail=f"{message.plugin_id} isn't connected, so the mail can't be read")
    try:
        proposed = await decide(message, client, provider, settings.ai_monthly_cap, chosen=choice.verb)
    except Exception as error:  # the plugin or the AI is down: nothing changed, the owner can try again
        logger.exception("Proposing %s for job %s failed", choice.verb, job_id)
        raise HTTPException(status_code=502, detail=f"couldn't get a {choice.verb} proposal, try again") from error
    replaced = proposed.model_dump(include={"verb", "title", "evidence", "artifacts", "due", "ask_owner", "suggested_verbs", "problems"})
    # Re-checked at write time: an approval may have sent it while the AI was proposing.
    fresh = {**replaced, "edited": False, "error": None, "reminder": None, "permission_level": None}  # the old action's
    stored = await Job.find({"_id": job_id, "state": "open", "sent_at": None}).update({"$set": fresh})
    if not stored.modified_count:
        raise HTTPException(status_code=409, detail=f"job {job_id} isn't open")
    return await owned(job_id, owner_id)


@router.post("/{job_id}/dismiss", response_model=Job)
async def dismiss_job(job_id: PydanticObjectId, owner_id: OwnerId, plugins: PluginRegistry = Depends(plugin_registry)) -> Job:
    await owned(job_id, owner_id)
    return await acting(lambda: finish(job_id, "dismissed", plugins, claim_from=("open", "failed")))
