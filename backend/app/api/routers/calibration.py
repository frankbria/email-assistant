"""Calibration (spec §10.7): start a dry run over recent mail, list its cards, and take the owner's reaction to one."""

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.routers.jobs import Choice, JobCard, learn_from_answer, message_of, plugin_registry
from app.auth import OwnerId
from app.config import Settings, get_settings
from app.models.calibration import CalibrationJob
from app.models.job import Job
from app.models.message import Message
from app.pipeline.calibrate import SAMPLE, add_to_test_set, calibrate
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import AIProvider, get_ai_provider

router = APIRouter(prefix="/api/v1/calibration", tags=["calibration"])


@router.post("", status_code=202)
async def start_calibration(
    owner_id: OwnerId,
    background: BackgroundTasks,
    sample: int = Query(SAMPLE, ge=1, le=500),
    plugins: PluginRegistry = Depends(plugin_registry),
    provider: AIProvider = Depends(get_ai_provider),
    settings: Settings = Depends(get_settings),
) -> None:
    """One AI call per message, so it runs after the answer; its cards appear as they're made."""
    background.add_task(calibrate, owner_id, plugins, provider, settings.ai_monthly_cap, sample)


@router.get("", response_model=list[JobCard])
async def list_calibration(owner_id: OwnerId) -> list[JobCard]:
    jobs = await CalibrationJob.find(CalibrationJob.owner_id == owner_id).to_list()
    messages = {message.id: message for message in await Message.find(In(Message.id, [job.message_ids[0] for job in jobs])).to_list()}
    cards = [(messages[job.message_ids[0]], job) for job in jobs if job.message_ids[0] in messages]
    return [
        JobCard(job=job, sender=message.sender, subject=message.subject, list_id=message.list_id)
        for message, job in sorted(cards, key=lambda card: card[0].date, reverse=True)
    ]


@router.post("/{job_id}/react", response_model=Job)
async def react(job_id: PydanticObjectId, choice: Choice, owner_id: OwnerId, settings: Settings = Depends(get_settings)) -> Job:
    """The owner's 👍 (the proposed verb), fix (another verb) or noise (archive_noise) on a card: an example, a rule
    with "always", and a test set line. Taking the card first means a double tap adds one line, not two."""
    taken = await CalibrationJob.get_pymongo_collection().find_one_and_delete({"_id": job_id, "owner_id": owner_id})
    if taken is None:
        raise HTTPException(status_code=404, detail="Calibration card not found")
    calibration = CalibrationJob.model_validate(taken)
    message = await message_of(calibration)
    add_to_test_set(settings.test_set_file, message, calibration, choice.verb)
    await learn_from_answer(message, calibration.text or message.snippet, choice, "calibration")
    calibration.state = "done"
    return calibration
