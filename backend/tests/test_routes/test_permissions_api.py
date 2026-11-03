# Permissions on the settings screen (spec §9, AC-K.3 UI half, AC-K.4): the API the screen uses, and the
# promotion offer after 10 unedited approvals in a row. Real MongoDB; a temporary permissions.yaml.
import asyncio
from pathlib import Path

import pytest
import yaml

from app.api.routers.permissions import permissions_path
from app.main import app
from app.permissions import PROMOTION_AFTER, PermissionSettings, level_for, promotion_offers, record_approval, set_levels
from tests.utils.auth import OWNER_ID


@pytest.fixture
def permissions_file(tmp_path: Path):
    path = tmp_path / "permissions.yaml"
    app.dependency_overrides[permissions_path] = lambda: path
    yield path
    app.dependency_overrides.pop(permissions_path)


async def streak(verb: str) -> None:
    for _ in range(PROMOTION_AFTER):
        await record_approval(OWNER_ID, verb, edited=False)


async def test_the_screen_gets_each_verb_with_its_level_and_ceiling(async_client, test_db, permissions_file: Path):
    response = await async_client.get("/api/v1/permissions")

    assert response.status_code == 200
    verbs = {row["verb"]: row for row in response.json()["verbs"]}
    assert verbs["unsubscribe"] == {"verb": "unsubscribe", "level": "never_auto", "default": "never_auto",
                                    "ceiling": "never_auto", "reason": "links in email are untrusted"}
    assert verbs["reply"]["ceiling"] == "autonomous" and verbs["reply"]["level"] == "ask"
    assert response.json()["promotions"] == [] and response.json()["file_error"] is None


async def test_a_change_is_stored_and_written_to_the_file(async_client, test_db, permissions_file: Path):
    response = await async_client.put("/api/v1/permissions/archive_noise", json={"level": "autonomous"})

    assert response.status_code == 200
    assert {row["verb"]: row["level"] for row in response.json()["verbs"]}["archive_noise"] == "autonomous"
    assert yaml.safe_load(permissions_file.read_text())["archive_noise"] == "autonomous"


@pytest.mark.parametrize(("verb", "level", "reason"), [
    ("unsubscribe", "autonomous", "unsubscribe can't be autonomous: its highest level is never_auto (links in email are untrusted)"),
    ("forward", "autonomous", "forward can't be autonomous: its highest level is ask (new recipients come from AI judgment)"),
    ("reply", "always", "reply: 'always' isn't a level (autonomous, ask or never_auto)"),
    ("frobnicate", "ask", "frobnicate isn't a verb"),
])
async def test_a_choice_the_ceilings_dont_allow_is_rejected_with_the_reason(async_client, test_db, permissions_file: Path, verb, level, reason):
    """AC-K.3 (UI half): the screen shows this message."""
    response = await async_client.put(f"/api/v1/permissions/{verb}", json={"level": level})

    assert (response.status_code, response.json()["detail"]) == (422, reason)


async def test_ten_unedited_approvals_in_a_row_offer_promotion_once(test_db):
    """AC-K.4: offered once, and nothing changes unless the owner accepts."""
    for _ in range(PROMOTION_AFTER - 1):
        await record_approval(OWNER_ID, "reply", edited=False)
    await record_approval(OWNER_ID, "reply", edited=True)  # an edit starts the streak over
    for _ in range(PROMOTION_AFTER - 1):
        await record_approval(OWNER_ID, "reply", edited=False)
    before = await promotion_offers(OWNER_ID)
    await record_approval(OWNER_ID, "reply", edited=False)
    offered = await promotion_offers(OWNER_ID)
    for _ in range(PROMOTION_AFTER * 2):
        await record_approval(OWNER_ID, "reply", edited=False)

    assert (before, offered) == ([], ["reply"])
    assert await promotion_offers(OWNER_ID) == ["reply"]  # the same single offer, not a new one
    assert await level_for(OWNER_ID, "reply") == "ask"  # never promoted on its own


async def test_verbs_that_cant_be_autonomous_or_already_are_arent_offered(test_db):
    await PermissionSettings(owner_id=OWNER_ID, levels={"archive_noise": "autonomous"}).insert()
    for verb in ("forward", "todo", "archive_noise"):
        for _ in range(PROMOTION_AFTER):
            await record_approval(OWNER_ID, verb, edited=False)

    assert await promotion_offers(OWNER_ID) == []


async def test_accepting_promotes_and_declining_doesnt_and_neither_offers_again(async_client, test_db, permissions_file: Path):
    await streak("reply")
    await streak("snooze")
    offered = (await async_client.get("/api/v1/permissions")).json()["promotions"]

    accepted = await async_client.post("/api/v1/permissions/promotions/reply", json={"accept": True})
    declined = await async_client.post("/api/v1/permissions/promotions/snooze", json={"accept": False})
    again = await async_client.post("/api/v1/permissions/promotions/snooze", json={"accept": True})
    await streak("snooze")  # another streak after the answer: the one offer was made

    levels = {row["verb"]: row["level"] for row in declined.json()["verbs"]}
    assert offered == ["reply", "snooze"]
    assert (accepted.status_code, declined.status_code, again.status_code) == (200, 200, 404)
    assert (levels["reply"], levels["snooze"]) == ("autonomous", "ask") and declined.json()["promotions"] == []
    assert await promotion_offers(OWNER_ID) == []
    assert yaml.safe_load(permissions_file.read_text())["reply"] == "autonomous"


async def test_an_offer_made_moot_by_a_manual_promotion_doesnt_come_back_after_a_downgrade(async_client, test_db, permissions_file: Path):
    await streak("reply")

    await async_client.put("/api/v1/permissions/reply", json={"level": "autonomous"})
    downgraded = await async_client.put("/api/v1/permissions/reply", json={"level": "ask"})

    assert downgraded.json()["promotions"] == []




async def test_overlapping_changes_both_survive(test_db, tmp_path: Path):
    """Each change rewrites all the settings (two settings pages, or a page and the file sync); neither may drop
    the other. Whether two overlap depends on timing, so several rounds flip both verbs."""
    path = tmp_path / "permissions.yaml"
    for raised in (True, False, True, False, True):
        expected = ("autonomous", "never_auto") if raised else ("ask", "ask")
        await asyncio.gather(
            set_levels(OWNER_ID, {"archive_noise": expected[0]}, path),
            set_levels(OWNER_ID, {"snooze": expected[1]}, path),
        )

        written = yaml.safe_load(path.read_text())
        assert (await level_for(OWNER_ID, "archive_noise"), await level_for(OWNER_ID, "snooze")) == expected
        assert (written["archive_noise"], written["snooze"]) == expected
