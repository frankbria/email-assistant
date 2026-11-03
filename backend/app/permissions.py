"""Per-verb permissions (spec §4 table, §9): one level per verb, kept in a readable permissions.yaml that
stays in sync with the stored settings. A level above a verb's ceiling is rejected with the reason."""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeGuard, get_args

import yaml
from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

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


class PermissionsRejected(ValueError):
    """The settings ask for something not allowed; the message says what and why."""


class PermissionSettings(Document):
    owner_id: str
    levels: dict[str, PermissionLevel] = Field(default_factory=dict)  # only what differs from DEFAULTS is needed
    file_mtime: float | None = None  # the permissions.yaml version last read or written
    file_error: str | None = None  # why the current file was rejected (shown on the settings screen)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "permission_settings"
        indexes = [IndexModel([("owner_id", ASCENDING)], unique=True)]


async def level_for(owner_id: str, verb: str) -> PermissionLevel:
    """The stored level, else the §4 default; a verb nobody has heard of asks (spec §9)."""
    settings = await PermissionSettings.find_one(PermissionSettings.owner_id == owner_id)
    stored = settings.levels if settings else {}
    return stored.get(verb) or DEFAULTS.get(verb, "ask")


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
    await write_file(settings, path)


async def write_file(settings: PermissionSettings, path: Path) -> None:
    path.write_text(render_permissions(settings.levels))
    settings.file_mtime, settings.file_error, settings.updated_at = path.stat().st_mtime, None, datetime.now(UTC)
    await settings.save()


async def sync_permissions_file(owner_id: str, path: Path) -> None:
    """Each pass: an edited file updates the store (or is rejected, keeping the store and saying why);
    a missing file is written from the store."""
    settings = await stored_settings(owner_id)
    if not path.exists():
        await write_file(settings, path)
        return
    mtime = path.stat().st_mtime
    if mtime == settings.file_mtime:
        return
    try:
        settings.levels = parse_permissions(path.read_text())
        settings.file_error = None
    except (PermissionsRejected, yaml.YAMLError) as error:
        settings.file_error = str(error)
        logger.error("permissions.yaml was rejected, keeping the current settings: %s", error)
    settings.file_mtime, settings.updated_at = mtime, datetime.now(UTC)
    await settings.save()
