"""The Filtered view (spec §10.5): everything archived as noise in the last 30 days. Restoring one is the History
undo (POST /api/v1/history/{id}/undo), so it teaches the stream to ask first like any restore of the app's archive."""

from datetime import UTC, datetime, timedelta

from beanie.operators import In
from fastapi import APIRouter
from mailbox_contract import Address
from pydantic import BaseModel

from app.auth import OwnerId
from app.models.action_log import ActionLogEntry
from app.models.job import Job
from app.models.message import Message

router = APIRouter(prefix="/api/v1/filtered", tags=["filtered"])
WINDOW = timedelta(days=30)


class FilteredCard(BaseModel):
    entry: ActionLogEntry
    sender: Address
    subject: str
    rationale: str | None
    restorable: bool


@router.get("", response_model=list[FilteredCard])
async def list_filtered(owner_id: OwnerId) -> list[FilteredCard]:
    """Only archive_noise archives: a digest is low-priority mail the owner read as a summary, not mail filtered
    out unseen, and a dismissal is the owner's own call."""
    # shortcut: the whole 30-day window, unpaged (like History); page it when an owner's noise volume shows it slow.
    entries = (
        await ActionLogEntry.find(
            ActionLogEntry.owner_id == owner_id,
            ActionLogEntry.action == "archived",
            {"undoable": True},  # it moved mail (a partly failed job too)
            ActionLogEntry.created_at >= datetime.now(UTC) - WINDOW,
        )
        .sort("-created_at", "-_id")
        .to_list()
    )
    noise_jobs = {
        job.id: job for job in await Job.find(In(Job.id, list({entry.job_id for entry in entries})), Job.verb == "archive_noise").to_list()
    }
    entries = [entry for entry in entries if entry.job_id in noise_jobs]
    messages = await Message.find(In(Message.id, list({message_id for entry in entries for message_id in entry.message_ids}))).to_list()
    by_id = {message.id: message for message in messages}
    cards = []
    for entry in entries:
        found = [by_id[message_id] for message_id in entry.message_ids if message_id in by_id]
        if not found:
            continue
        cards.append(
            FilteredCard(
                entry=entry,
                sender=found[0].sender,
                subject=found[0].subject,
                rationale=noise_jobs[entry.job_id].artifacts.noise_rationale,
                restorable=entry.undoable and not entry.undone,
            )
        )
    return cards
