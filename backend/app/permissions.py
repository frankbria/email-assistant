"""Per-verb permissions (spec §4 table, §9): one level per verb, kept in a readable permissions.yaml that
stays in sync with the stored settings. A level above a verb's ceiling is rejected with the reason."""

import hashlib
import logging
import os
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeGuard, get_args

import yaml
from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel, ReturnDocument

from app.models.job import PermissionLevel, Verb

logger = logging.getLogger(__name__)

LEVELS: tuple[PermissionLevel, ...] = ("never_auto", "ask", "autonomous")  # lowest to highest
# Spec §4: the default for each verb, and the highest level it may have with why.
ASK: PermissionLevel = "ask"
DEFAULTS: dict[str, PermissionLevel] = {verb: ASK for verb in get_args(Verb)} | {"unsubscribe": "never_auto"}
CEILINGS: dict[str, tuple[PermissionLevel, str]] = {
    "reply": ("autonomous", "only to the original sender, with no new recipients"),
    "forward": ("ask", "new recipients come from AI judgment"),
    "digest": ("autonomous", "finishing it archives all of its mail"),
    "snooze": ("autonomous", "it only hides the job until its date"),
    "follow_up": ("autonomous", "it only reminds the owner"),
    "todo": ("ask", "completing it needs the owner"),
    "archive_noise": ("autonomous", "archived mail can be restored"),
    "unsubscribe": ("never_auto", "links in email are untrusted"),
}


PROMOTION_AFTER = 10  # spec §9 [Call]: approvals in a row, with no edits, before promotion is offered


class PermissionsRejected(ValueError):
    """The settings ask for something not allowed; the message says what and why."""


class PermissionSettings(Document):
    owner_id: str
    levels: dict[str, PermissionLevel] = Field(default_factory=dict)  # only what differs from DEFAULTS is needed
    file_hash: str | None = None  # sha256 of the permissions.yaml content last read or written
    file_error: str | None = None  # why the current file was rejected (shown on the settings screen)
    write_pending: bool = False  # the store changed but the file couldn't be written: the store is newer
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "permission_settings"
        indexes = [IndexModel([("owner_id", ASCENDING)], unique=True)]


async def level_for(owner_id: str, verb: str) -> PermissionLevel:
    """The stored level, else the §4 default; a verb nobody has heard of asks (spec §9)."""
    settings = await PermissionSettings.find_one(PermissionSettings.owner_id == owner_id)
    level = (settings.levels if settings else {}).get(verb) or DEFAULTS.get(verb, "ask")
    ceiling = CEILINGS.get(verb, ("ask", ""))[0]
    return min(level, ceiling, key=LEVELS.index)  # a ceiling lowered later still holds


def is_level(value: object) -> TypeGuard[PermissionLevel]:
    return value in LEVELS


def validated(levels: Iterable[tuple[object, object]]) -> dict[str, PermissionLevel]:
    checked: dict[str, PermissionLevel] = {}
    for verb, level in levels:
        if not isinstance(verb, str) or verb not in CEILINGS:
            raise PermissionsRejected(f"{verb} isn't a verb")
        if not is_level(level):
            raise PermissionsRejected(f"{verb}: {level!r} isn't a level (autonomous, ask or never_auto)")
        ceiling, reason = CEILINGS[verb]
        if LEVELS.index(level) > LEVELS.index(ceiling):
            raise PermissionsRejected(f"{verb} can't be {level}: its highest level is {ceiling} ({reason})")
        checked[verb] = level
    return checked


def parse_permissions(text: str) -> dict[str, PermissionLevel]:
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise PermissionsRejected("permissions.yaml must map each verb to a level")
    return validated(loaded.items())


def render_permissions(levels: dict[str, PermissionLevel]) -> str:
    lines = ["# One permission per verb: autonomous, ask or never_auto. Kept in sync with the settings screen.",
             "# A verb can't go above its highest level (after the #)."]
    for verb, (ceiling, reason) in CEILINGS.items():
        lines.append(f"{verb}: {levels.get(verb) or DEFAULTS[verb]}  # highest: {ceiling} ({reason})")
    return "\n".join(lines) + "\n"


async def stored_settings(owner_id: str) -> PermissionSettings:
    return await PermissionSettings.find_one(PermissionSettings.owner_id == owner_id) or PermissionSettings(owner_id=owner_id)


async def set_levels(owner_id: str, levels: dict[str, PermissionLevel], path: Path) -> None:
    """The settings screen's change: validated like the file, stored, then written to the file."""
    settings = await stored_settings(owner_id)
    settings.levels |= validated(levels.items())
    settings.updated_at = datetime.now(UTC)
    await settings.save()  # stored first: a file that can't be written never loses the change
    await write_file(settings, path)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def write_file(settings: PermissionSettings, path: Path) -> None:
    """Atomically (temp file + rename), so a crash or a reader never sees half a file."""
    text = render_permissions(settings.levels)
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".permissions-", delete=False) as temporary:
            temporary.write(text)
        os.replace(temporary.name, path)
        settings.file_hash, settings.file_error, settings.write_pending = digest(text), None, False
    except OSError as error:
        settings.file_error, settings.write_pending = f"couldn't write {path}: {error.strerror or error}", True
        logger.error("Couldn't write permissions.yaml: %s", error)
    await settings.save()


async def sync_permissions_file(owner_id: str, path: Path) -> None:
    """Each pass: an edited file updates the store (or is rejected, keeping the store and saying why);
    a missing or empty file (a truncated write) is written from the store, never read as all defaults."""
    settings = await stored_settings(owner_id)
    text = path.read_text() if path.exists() else ""
    if settings.write_pending or not text.strip():  # the store is newer than the file: never read it back
        await write_file(settings, path)
        return
    if digest(text) == settings.file_hash:
        return  # compared by content: an edit in the same clock tick still counts
    try:
        settings.levels = parse_permissions(text)
        settings.file_error = None
    except (PermissionsRejected, yaml.YAMLError) as error:
        settings.file_error = str(error)
        logger.error("permissions.yaml was rejected, keeping the current settings: %s", error)
    settings.file_hash, settings.updated_at = digest(text), datetime.now(UTC)
    await settings.save()


class ApprovalStreak(Document):
    """Approvals in a row of one verb with no edits (spec §9 promotion). Offered once, never applied alone."""

    owner_id: str
    verb: str
    in_a_row: int = 0  # not `count`: that's Document.count()
    offered: bool = False  # the one offer was made (accepted or not, it isn't made again)
    offer_pending: bool = False  # waiting for the owner's answer

    class Settings:
        name = "approval_streaks"
        indexes = [IndexModel([("owner_id", ASCENDING), ("verb", ASCENDING)], unique=True)]


async def record_approval(owner_id: str, verb: str, edited: bool) -> None:
    """Called when the owner approves a job (#74). An edit starts the streak over; the PROMOTION_AFTER-th
    unedited approval in a row offers promotion once, if the verb may be autonomous and isn't yet."""
    streaks = ApprovalStreak.get_pymongo_collection()
    key = {"owner_id": owner_id, "verb": verb}
    if edited:
        await streaks.update_one(key, {"$set": {"in_a_row": 0}}, upsert=True)
        return
    streak = await streaks.find_one_and_update(key, {"$inc": {"in_a_row": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    assert streak is not None  # an upsert returning the document after it always has one
    if streak["in_a_row"] >= PROMOTION_AFTER and not streak.get("offered") and await promotable(owner_id, verb):
        await streaks.update_one({**key, "offered": {"$ne": True}}, {"$set": {"offered": True, "offer_pending": True}})


async def promotable(owner_id: str, verb: str) -> bool:
    return CEILINGS.get(verb, ("ask", ""))[0] == "autonomous" and await level_for(owner_id, verb) != "autonomous"


async def promotion_offers(owner_id: str) -> list[str]:
    """Verbs whose promotion offer waits for the owner. An offer no longer worth making (the verb went
    autonomous another way) closes for good, so a later downgrade doesn't bring it back."""
    pending = await ApprovalStreak.find(ApprovalStreak.owner_id == owner_id, {"offer_pending": True}).to_list()
    offers = []
    for streak in pending:
        if await promotable(owner_id, streak.verb):
            offers.append(streak.verb)
        else:
            await streak.set({"offer_pending": False})
    return sorted(offers)


async def answer_promotion(owner_id: str, verb: str, accept: bool, path: Path) -> bool:
    """The owner's answer to the one offer: accept makes the verb autonomous. False if nothing was offered."""
    streaks = ApprovalStreak.get_pymongo_collection()
    pending = {"owner_id": owner_id, "verb": verb, "offer_pending": True}
    if not await streaks.find_one(pending):
        return False
    if accept:  # promoted before the offer closes: a crash between them leaves an offer no longer shown, not a lost yes
        await set_levels(owner_id, {verb: "autonomous"}, path)
    await streaks.update_one(pending, {"$set": {"offer_pending": False}})
    return True
