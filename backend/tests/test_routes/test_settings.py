# The settings screen's API (spec §10.9): AI provider and model, poll interval and first-connect window, stored per
# owner; the env values are the defaults until the owner saves their own. Real MongoDB; GreenMail for the sync cadence.
import asyncio
from collections.abc import Iterator

import httpx
import pytest

from app.config import get_settings
from app.main import app
from app.models.sync_cursor import SyncCursor
from app.models.message import Message
from app.services.ai_provider import AnthropicProvider, get_ai_provider
from app.sync import SyncEngine
from tests.conformance.test_mailbox_conformance import reference_imap_plugin
from tests.test_sync.test_inbox_sync import PLUGIN, add_owner, connected, eventually
from tests.utils.auth import OWNER_ID, bearer_headers
from tests.utils.mail_server import Mailbox

CHOSEN = {"ai_provider": "anthropic", "ai_model": "claude-sonnet-5-5", "poll_seconds": 300, "first_connect_days": 30}


@pytest.fixture
def env_defaults(monkeypatch) -> Iterator[None]:
    for variable, value in {"AI_MODEL": "claude-env-model", "SYNC_POLL_SECONDS": "90", "FIRST_CONNECT_DAYS": "7"}.items():
        monkeypatch.setenv(variable, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_an_owner_who_has_not_chosen_gets_the_env_values(test_db, async_client, env_defaults):
    response = await async_client.get("/api/v1/settings")

    assert response.status_code == 200
    assert {key: response.json()[key] for key in CHOSEN} == {
        "ai_provider": "anthropic", "ai_model": "claude-env-model", "poll_seconds": 90, "first_connect_days": 7
    }


async def test_saved_settings_are_returned_to_their_owner_only(test_db, async_client):
    saved = await async_client.put("/api/v1/settings", json=CHOSEN)
    other_owner = await async_client.get("/api/v1/settings", headers=bearer_headers("someone-else"))

    assert saved.status_code == 200
    assert {key: (await async_client.get("/api/v1/settings")).json()[key] for key in CHOSEN} == CHOSEN
    assert other_owner.json()["ai_model"] == get_settings().ai_model


async def test_settings_the_forwarding_model_used_are_gone_even_from_a_document_saved_with_them(test_db, async_client):
    await test_db["user_settings"].insert_one({"user_id": OWNER_ID, "enable_spam_filtering": True, "skip_low_priority_emails": False})

    returned = (await async_client.get("/api/v1/settings")).json()

    assert returned["poll_seconds"] == get_settings().sync_poll_seconds
    assert not {"enable_spam_filtering", "enable_auto_categorization", "skip_low_priority_emails"} & returned.keys()


@pytest.mark.parametrize(
    "change",
    [
        {"ai_provider": "openai"},
        {"ai_model": ""},
        {"ai_model": "   "},
        {"ai_model": "m" * 201},
        {"poll_seconds": 4},
        {"poll_seconds": 86401},
        {"first_connect_days": 0},
        {"first_connect_days": 366},
    ],
    ids=str,
)
async def test_out_of_range_or_unsupported_values_are_rejected(test_db, async_client, change):
    response = await async_client.put("/api/v1/settings", json=CHOSEN | change)

    assert response.status_code == 422
    assert (await async_client.get("/api/v1/settings")).json()["ai_model"] == get_settings().ai_model


async def test_a_partial_update_is_rejected(test_db, async_client):
    response = await async_client.put("/api/v1/settings", json={"poll_seconds": 300})

    assert response.status_code == 422


async def test_the_next_ai_call_uses_the_newly_chosen_model(test_db, async_client):
    before = await get_ai_provider(OWNER_ID)
    await async_client.put("/api/v1/settings", json=CHOSEN)
    after = await get_ai_provider(OWNER_ID)

    assert isinstance(before, AnthropicProvider) and before.model == get_settings().ai_model
    assert isinstance(after, AnthropicProvider) and after.model == "claude-sonnet-5-5"


async def test_changing_the_poll_interval_changes_the_sync_cadence_without_a_restart(test_db, mailbox: Mailbox):
    """AC: the engine starts on an hour's interval; after the owner picks 5 s through the API, mail arrives within it."""
    await add_owner(test_db, OWNER_ID)
    async with connected(reference_imap_plugin(mailbox)) as registry:
        engine = SyncEngine(registry, test_db["user"], poll_seconds=3600)
        app.state.sync = engine
        running = asyncio.create_task(engine.run())
        try:
            await eventually(lambda: SyncCursor.find_one(SyncCursor.plugin_id == PLUGIN).exists())
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", headers=bearer_headers()
            ) as api:
                assert (await api.put("/api/v1/settings", json=CHOSEN | {"poll_seconds": 5})).status_code == 200
            first = mailbox.deliver(sender="a@example.com", subject="First", body="x")
            await eventually(lambda: Message.find_one(Message.message_id == first).exists(), timeout_seconds=10)
            second = mailbox.deliver(sender="a@example.com", subject="Second", body="x")

            # Within two of the new intervals, where the old one would have waited an hour.
            await eventually(lambda: Message.find_one(Message.message_id == second).exists(), timeout_seconds=10)
        finally:
            running.cancel()
            await asyncio.wait({running})
            del app.state.sync
