# Job and message data model (#54, spec §4, §5.3) against real MongoDB.
from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId
from mailbox_contract import Address
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.models.job import Artifacts, Job
from app.models.message import Message
from app.models.sync_cursor import SyncCursor
from tests.utils.auth import OWNER_ID


def message(ref: str, message_id: str, plugin_id: str = "proton") -> Message:
    return Message(
        owner_id=OWNER_ID,
        plugin_id=plugin_id,
        ref=ref,
        message_id=message_id,
        sender=Address(name="Dana", email="dana@example.com"),
        to=[Address(email="owner@example.com")],
        cc=[],
        date=datetime(2026, 11, 2, 9, 0, tzinfo=UTC),
        subject="Lunch Thursday?",
        snippet="Are you free at noon",
    )


def job(verb: str, title: str, messages: list[Message], artifacts: Artifacts) -> Job:
    return Job(
        owner_id=OWNER_ID,
        verb=verb,
        title=title,
        evidence=["Are you free at noon"],
        artifacts=artifacts,
        message_ids=[saved.id for saved in messages],
    )


async def test_one_message_can_be_referenced_by_many_jobs(test_db):
    lunch = await message("proton:1", "<lunch@example.com>").insert()
    reply = await job("reply", "Answer Dana about Thursday lunch", [lunch], Artifacts(draft="Noon works.")).insert()
    reminder = await job("follow_up", "Chase Dana if no answer", [lunch], Artifacts(draft="Still on?")).insert()

    jobs_for_lunch = await Job.find(Job.message_ids == lunch.id).to_list()

    assert {found.id for found in jobs_for_lunch} == {reply.id, reminder.id}


async def test_a_job_can_reference_many_messages(test_db):
    newsletters = [await message(f"proton:{n}", f"<news-{n}@example.com>").insert() for n in range(3)]
    digest = await job("digest", "3 newsletters this week", newsletters, Artifacts(digest="Rates up; two sales.")).insert()

    stored = await Job.get(digest.id)
    referenced = await Message.find({"_id": {"$in": stored.message_ids}}).to_list()

    assert stored.state == "open"
    assert {found.ref for found in referenced} == {"proton:0", "proton:1", "proton:2"}


async def test_the_same_message_id_in_two_accounts_is_two_messages_one_job_can_share(test_db):
    in_proton = await message("proton:7", "<shared@example.com>").insert()
    in_gmail = await message("gmail:42", "<shared@example.com>", plugin_id="gmail").insert()

    copies = await Message.find(Message.owner_id == OWNER_ID, Message.message_id == "<shared@example.com>").to_list()

    assert {copy.id for copy in copies} == {in_proton.id, in_gmail.id}


async def test_messages_are_indexed_on_message_id_and_ref(test_db):
    indexes = await Message.get_pymongo_collection().index_information()

    keys = {tuple(field for field, _ in index["key"]) for index in indexes.values()}
    assert ("owner_id", "message_id") in keys
    assert ("owner_id", "plugin_id", "ref") in keys


async def test_a_ref_is_stored_once_per_account(test_db):
    await message("proton:1", "<lunch@example.com>").insert()

    with pytest.raises(DuplicateKeyError):
        await message("proton:1", "<lunch@example.com>").insert()


async def test_jobs_are_indexed_on_the_messages_they_reference(test_db):
    indexes = await Job.get_pymongo_collection().index_information()

    keys = {tuple(field for field, _ in index["key"]) for index in indexes.values()}
    assert ("owner_id", "message_ids") in keys


def test_a_job_state_outside_the_lifecycle_is_rejected():
    with pytest.raises(ValidationError, match="state"):
        Job(owner_id=OWNER_ID, verb="reply", title="t", state="archived", artifacts=Artifacts(draft="d"), message_ids=[PydanticObjectId()])


def test_a_job_without_a_message_is_rejected():
    with pytest.raises(ValidationError, match="message_ids"):
        Job(owner_id=OWNER_ID, verb="todo", title="t", artifacts=Artifacts(link="https://example.com"), message_ids=[])


async def test_one_sync_cursor_per_plugin_and_folder(test_db):
    await SyncCursor(owner_id=OWNER_ID, plugin_id="proton", folder="inbox", cursor="uid:10").insert()
    await SyncCursor(owner_id=OWNER_ID, plugin_id="proton", folder="sent", cursor="uid:3").insert()

    with pytest.raises(DuplicateKeyError):
        await SyncCursor(owner_id=OWNER_ID, plugin_id="proton", folder="inbox", cursor="uid:11").insert()
