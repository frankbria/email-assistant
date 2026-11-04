# backend/app/api/routers/jobs.py
"""The job queue (spec §10.1, §10.2, §10.4): the owner's open jobs, and what the owner does with one: approve it
(the executor acts), edit its artifacts, choose another action (a fresh proposal for that verb), dismiss it, or
correct it, which also teaches a rule and an example."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, Self

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.auth import OwnerId
from app.config import Settings, get_settings
from app.executor import STALE_SENDING, JobNotOpen, defer, execute, finish, unsubscribe, unsubscribe_target_of
from app.models.example import ExampleSource
from app.models.job import Artifacts, Job, PermissionLevel, Verb
from app.models.message import Message
from app.permissions import level_for, record_approval
from app.pipeline.examples import record_example
from app.pipeline.rules import forget_noise_rules, learn_rule
from app.pipeline.run import decide
from app.pipeline.validate import ask_owner_job
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
    list_id: str | None  # the raw List-Id header: an "always" rule keys on it before the sender


class JobEdit(BaseModel):
    """The owner's changes to a job's artifacts; only the fields sent change."""

    draft: str | None = None
    forward_to: str | None = None
    options: list[str] = Field(default_factory=list)
    link: str | None = None
    due: datetime | None = None


class Seen(BaseModel):
    # The messages the owner's card showed; a digest gathers mail, so its tap covers only these (required for one).
    message_ids: list[PydanticObjectId] | None = None


class Approval(Seen):
    forward_to: str | None = None  # a forward's recipient as the owner confirmed it (never the AI's suggestion alone)
    unsubscribe_target: str | None = None  # the target the owner was shown, and for an https link opened themselves


class Choice(BaseModel):
    verb: Verb
    always: bool = False  # "always do this for this sender/list": a rule decides their next messages


class Correction(BaseModel):
    kind: Literal["wrong_action", "noise", "not_noise"]
    verb: Verb | None = None  # the right action, for a wrong action

    @model_validator(mode="after")
    def names_the_right_action(self) -> Self:
        if self.kind == "wrong_action" and self.verb is None:
            raise ValueError("say which action is right")
        return self


async def owned(job_id: PydanticObjectId, owner_id: str) -> Job:
    job = await Job.find_one(Job.id == job_id, Job.owner_id == owner_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def for_one_message(job_id: PydanticObjectId, owner_id: str) -> Job:
    """Another action, a correction or an edit is about one message, while a digest's done archives all of them."""
    job = await owned(job_id, owner_id)
    if job.verb == "digest" and len(job.message_ids) > 1 and len(await distinct_emails(job)) > 1:
        raise HTTPException(status_code=409, detail="a digest speaks for several messages; approve or dismiss it, or archive them one by one")
    return job


async def distinct_emails(job: Job) -> set[str]:
    """Copies of one email in several accounts share its Message-ID; mail without one counts on its own."""
    messages = await Message.find(In(Message.id, job.message_ids)).to_list()
    return {message.message_id or str(message.id) for message in messages}


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
        JobCard(job=job, sender=message.sender, subject=message.subject, list_id=message.list_id)
        for job in jobs
        if (message := by_id.get(job.message_ids[0]))
    ]


@router.patch("/{job_id}", response_model=Job)
async def edit_job(job_id: PydanticObjectId, edit: JobEdit, owner_id: OwnerId) -> Job:
    await for_one_message(job_id, owner_id)
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
    messages = shown_messages(job, approval)
    level = await tapped_level(owner_id, job.verb)
    actions: dict[str, Callable[[], Awaitable[Job]]] = {
        "reply": lambda: execute(job_id, plugins, forward_to=approval.forward_to, by="owner", level=level),
        "forward": lambda: execute(job_id, plugins, forward_to=approval.forward_to, by="owner", level=level),
        "snooze": lambda: defer(job_id, by="owner", level=level),
        "follow_up": lambda: defer(job_id, by="owner", level=level),
        "unsubscribe": lambda: unsubscribe(job_id, plugins, approval.unsubscribe_target, level=level),
    }
    acted = await acting(actions.get(job.verb, lambda: finish(job_id, "done", plugins, verb=job.verb, by="owner", level=level, messages=messages)))
    if acted.state in ("done", "snoozed"):
        # shortcut: a DB failure after the action and before this write loses this one streak tick (the job is final, so
        # a retry gets 409); move it into the executor if promotion offers ever need the streak exact.
        await record_approval(owner_id, job.verb, edited=acted.edited)
    return await owned(job_id, owner_id)


class UnsubscribeTarget(BaseModel):
    target: str  # an https link or a mailto, shown to the owner in full before they act on it


@router.get("/{job_id}/unsubscribe", response_model=UnsubscribeTarget)
async def show_unsubscribe_target(
    job_id: PydanticObjectId, owner_id: OwnerId, plugins: PluginRegistry = Depends(plugin_registry)
) -> UnsubscribeTarget:
    await owned(job_id, owner_id)
    try:
        return UnsubscribeTarget(target=await unsubscribe_target_of(job_id, plugins))
    except ValueError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused


async def tapped_level(owner_id: str, verb: Verb) -> PermissionLevel:
    """The owner's tap is the `ask` path whatever the verb's level; never_auto verbs say so."""
    return "never_auto" if await level_for(owner_id, verb) == "never_auto" else "ask"


@router.post("/{job_id}/choose", response_model=Job)
async def choose_action(
    job_id: PydanticObjectId,
    choice: Choice,
    owner_id: OwnerId,
    plugins: PluginRegistry = Depends(plugin_registry),
    provider: AIProvider = Depends(get_ai_provider),
    settings: Settings = Depends(get_settings),
) -> Job:
    """Spec §10.2: an ask-owner card's answer is kept as an example, and "always" teaches a rule, once the job
    has the chosen proposal. Another action chosen for a proposed job is no answer to a question, so it's no example;
    teaching from it is the correction's job (§10.4)."""
    job = await for_one_message(job_id, owner_id)
    message = await message_of(job)
    chosen = await propose_instead(job, message, choice.verb, plugins, provider, settings)
    if not job.ask_owner:  # another action for a proposed job answers no question; teaching from it is /correct's
        return chosen
    await learn_from_answer(message, message.snippet, choice, "ask_owner")
    return chosen


async def learn_from_answer(message: Message, body: str, choice: Choice, source: ExampleSource) -> None:
    """The ask-owner card's answer is an example, and "always" a rule. The choice is already made, so a failed lesson
    mustn't become an error; each lesson stands on its own."""
    try:
        await record_example(message, body, choice.verb, source)
    except Exception:
        logger.exception("Couldn't record the example for message %s", message.id)
    if choice.always:
        try:
            # the card names the stream ("for <list or sender>"), so the rule keys on it, not on a broader rule
            await learn_rule(message, choice.verb, correct_the_deciding_rule=False)
        except Exception:
            logger.exception("Couldn't learn the rule for message %s", message.id)


async def message_of(job: Job) -> Message:
    message = await Message.get(job.message_ids[0])
    assert message is not None, "a job's messages are stored before it"
    return message


async def propose_instead(
    job: Job, message: Message, verb: Verb, plugins: PluginRegistry, provider: AIProvider, settings: Settings
) -> Job:
    """A fresh proposal for `verb` replaces the job's."""
    if job.state not in IN_QUEUE or job.sent_at is not None:
        raise HTTPException(status_code=409, detail=f"job {job.id} isn't open")
    client = plugins.clients.get(message.plugin_id)
    if client is None:
        raise HTTPException(status_code=409, detail=f"{message.plugin_id} isn't connected, so the mail can't be read")
    try:
        proposed = await decide(message, client, provider, settings.ai_monthly_cap, chosen=verb)
    except Exception as error:  # the plugin or the AI is down: nothing changed, the owner can try again
        logger.exception("Proposing %s for job %s failed", verb, job.id)
        raise HTTPException(status_code=502, detail=f"couldn't get a {verb} proposal, try again") from error
    return await replace_proposal(job, proposed)


async def replace_proposal(job: Job, proposed: Job) -> Job:
    replaced = proposed.model_dump(include={"verb", "title", "evidence", "artifacts", "due", "ask_owner", "suggested_verbs", "problems"})
    # Re-checked at write time: an approval may have sent it, or mail may have joined it (a digest), while the AI
    # was proposing; the proposal speaks only for the messages it was made for.
    # A failed job (its send didn't go out) is back to open with the new proposal.
    fresh = {**replaced, "state": "open", "edited": False, "error": None, "reminder": None, "permission_level": None}  # the old action's
    stored = await Job.find(
        {"_id": job.id, "state": {"$in": IN_QUEUE}, "sent_at": None, "message_ids": job.message_ids}
    ).update({"$set": fresh})
    if not stored.modified_count:
        raise HTTPException(status_code=409, detail=f"job {job.id} isn't open or its mail changed, try again")
    assert job.id is not None
    return await owned(job.id, job.owner_id)


@router.post("/{job_id}/dismiss", response_model=Job)
async def dismiss_job(
    job_id: PydanticObjectId, owner_id: OwnerId, seen: Seen | None = None, plugins: PluginRegistry = Depends(plugin_registry)
) -> Job:
    messages = shown_messages(await owned(job_id, owner_id), seen or Seen())
    return await acting(lambda: finish(job_id, "dismissed", plugins, claim_from=("open", "failed"), by="owner", level=None, messages=messages))


def shown_messages(job: Job, seen: Seen) -> list[PydanticObjectId] | None:
    """A digest's tap must say which messages it covers; other jobs may (finish then refuses if they changed)."""
    if job.verb == "digest" and seen.message_ids is None:
        raise HTTPException(status_code=422, detail="say which messages of the digest you saw")
    return seen.message_ids


@router.post("/{job_id}/correct", response_model=Job)
async def correct_job(
    job_id: PydanticObjectId,
    correction: Correction,
    owner_id: OwnerId,
    plugins: PluginRegistry = Depends(plugin_registry),
    provider: AIProvider = Depends(get_ai_provider),
    settings: Settings = Depends(get_settings),
) -> Job:
    """Spec §10.4: the job is put right first; only then does the correction teach a rule for the mail's sender
    or list, effective on the next matching message, and an example. "This isn't noise" names no verb, so it
    forgets the noise rule and leaves the choice, and the example, to the owner's ask-owner card."""
    job = await for_one_message(job_id, owner_id)
    message = await message_of(job)
    if correction.kind == "not_noise":
        if job.verb != "archive_noise" or job.ask_owner:
            raise HTTPException(status_code=422, detail="this job isn't noise")
        corrected = await replace_proposal(job, ask_owner_job(message, ["you said this isn't noise"], []))
    elif correction.kind == "noise":
        corrected = await archive_as_noise(job, message, plugins)
    else:
        assert correction.verb is not None  # the model validator requires it
        corrected = await propose_instead(job, message, correction.verb, plugins, provider, settings)
    try:  # the job is already put right: a failed lesson mustn't turn that into an error the owner can't retry
        if correction.kind == "not_noise":
            await forget_noise_rules(message)
        else:
            verb: Verb | None = "archive_noise" if correction.kind == "noise" else correction.verb
            assert verb is not None
            await learn_rule(message, verb)
            await record_example(message, message.snippet, verb, "correction")
    except Exception:
        logger.exception("Couldn't learn from the correction of job %s", job_id)
    return corrected


async def archive_as_noise(job: Job, message: Message, plugins: PluginRegistry) -> Job:
    """The job becomes the owner's own archive_noise job and the executor archives its mail, as approving it would."""
    job_id = job.id
    assert job_id is not None
    # Nothing of the old action survives: its title, quotes, date and messages were about another verb.
    noise: dict[str, object] = {"verb": "archive_noise", "title": message.subject.strip() or "(no subject)", "evidence": [], "due": None,
             "ask_owner": False, "suggested_verbs": [], "problems": [], "edited": False, "error": None, "reminder": None,
             "artifacts": Artifacts(noise_rationale="you marked this as noise").model_dump()}
    # Only over the mail the owner judged: a digest may have gathered more since the guard (see replace_proposal).
    marked = await Job.find(
        {"_id": job_id, "state": {"$in": IN_QUEUE}, "sent_at": None, "message_ids": job.message_ids}
    ).update({"$set": noise})
    if not marked.matched_count:
        raise HTTPException(status_code=409, detail=f"job {job_id} isn't open or its mail changed, try again")
    level = await tapped_level(job.owner_id, "archive_noise")
    return await acting(lambda: finish(job_id, "done", plugins, claim_from=("open", "failed"), verb="archive_noise", by="owner", level=level))
