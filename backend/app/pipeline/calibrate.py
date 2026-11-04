"""Calibration (spec §10.7): the pipeline's proposals for the owner's recent mail, made as a dry run. Only `decide` runs,
whose one plugin call is the `get_message` read; nothing is stored as a job, so nothing acts. The owner's reactions
(the ask-owner card's answer) become examples, optional rules and lines of the local test set."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pymongo.errors import DuplicateKeyError

from app.models.calibration import CalibrationJob
from app.models.job import Verb
from app.models.message import Message
from app.pipeline.minimize import minimize
from app.pipeline.run import decide
from app.plugins.calls import call_plugin
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import AIProvider
from mailbox_contract import MessageDetail

logger = logging.getLogger(__name__)
SAMPLE = 100


async def calibrate(owner_id: str, plugins: PluginRegistry, provider: AIProvider, cap: int | None, sample: int = SAMPLE) -> None:
    """Proposals for the owner's `sample` newest inbox messages; a new run replaces the last one's unanswered cards.
    A message that can't be read or proposed for is left out, like one whose plugin isn't connected."""
    await CalibrationJob.find(CalibrationJob.owner_id == owner_id).delete()
    recent = Message.find(Message.owner_id == owner_id, Message.folder == "inbox")
    for message in await recent.sort("-date").limit(sample).to_list():
        client = plugins.clients.get(message.plugin_id)
        if client is None:
            continue
        try:
            # read again for the test set: decide keeps no text
            detail = MessageDetail.model_validate(await call_plugin(message.plugin_id, client, "get_message", {"ref": message.ref}))
            job = await decide(message, client, provider, cap)
        except Exception:
            logger.exception("Calibration left out message %s", message.id)
            continue
        proposed = None if job.ask_owner else job.verb
        # The AI's verb is the card's one-tap answer (the owner's 👍); another verb is the owner's fix.
        card = CalibrationJob(
            **job.model_dump(exclude={"id", "revision_id", "ask_owner", "suggested_verbs"}),
            ask_owner=True, suggested_verbs=[proposed] if proposed else job.suggested_verbs,
            proposed=proposed, text=minimize(detail.text, message.subject),
        )
        await replace_card(owner_id, message, card)


async def replace_card(owner_id: str, message: Message, card: CalibrationJob) -> None:
    """The message's one card, replacing one an overlapping run stored; the unique index makes a lost race fail."""
    collection = CalibrationJob.get_pymongo_collection()
    same_message = {"owner_id": owner_id, "message_ids": message.id}
    document = card.model_dump(by_alias=True, exclude={"id", "revision_id"})
    try:
        await collection.replace_one(same_message, document, upsert=True)
    except DuplicateKeyError:  # the other run inserted between our match and our insert: replace what it stored
        await collection.replace_one(same_message, document)

def add_to_test_set(path: str, message: Message, calibration: CalibrationJob, verb: Verb) -> None:
    """One JSON line per reaction: the mail, what the AI proposed and what the owner said it should be."""
    entry = {
        "message_id": message.message_id, "sender": message.sender.email, "list_id": message.list_id,
        "subject": message.subject, "text": calibration.text, "proposed": calibration.proposed, "owner_verb": verb,
        "reacted_at": datetime.now(UTC).isoformat(),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as test_set:
        test_set.write(json.dumps(entry, ensure_ascii=False) + "\n")
