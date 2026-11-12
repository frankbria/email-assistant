# backend/tests/conftest.py

import os
import sys
from datetime import UTC

# Ensure imports resolve properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import httpx
import pytest
from beanie import init_beanie
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

# App imports
from app.api.routers.jobs import plugin_registry
from app.main import app
from app.models.action_log import ActionLogEntry
from app.models.ai_usage import AiUsage
from app.models.calibration import CalibrationJob
from app.models.example import Example
from app.models.job import Job
from app.models.message import Message
from app.models.rule import Rule
from app.models.sync_cursor import SyncCursor
from app.models.user_settings import UserSettings
from app.permissions import ApprovalStreak, PermissionSettings
from app.services.ai_provider import get_ai_provider, provider_for
from tests.utils.auth import AUTH_BASE_URL, bearer_headers
from tests.utils.fakes import FakeAIProvider

# Load environment variables
load_dotenv()

# Set test environment variables (override as needed)
os.environ["MONGODB_URI"] = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
os.environ["MONGODB_DB"] = os.getenv("MONGODB_TEST_DB", "email_assistant_test")

# Better Auth stand-in: a real local JWKS endpoint for test-minted tokens.
os.environ["BETTER_AUTH_URL"] = AUTH_BASE_URL

# ---------------------
# Core Fixtures
# ---------------------


@pytest.fixture(scope="function")
async def test_db():
    """Initialize test database connection and Beanie."""
    mongo_uri = os.environ["MONGODB_URI"]
    test_db_name = os.environ["MONGODB_DB"]

    print(f"Using test database: {mongo_uri}/{test_db_name}")

    if "_test" not in test_db_name.lower():
        raise ValueError("Test is attempting to use production database! Aborting.")

    # pytest-asyncio (auto mode) runs this fixture and the test in the same
    # function-scoped loop, so the client lives and dies with that loop.
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(mongo_uri, tz_aware=True, tzinfo=UTC)

    db = client[test_db_name]

    document_models = [
        UserSettings,
        Message,
        Job,
        SyncCursor,
        Rule,
        AiUsage,
        PermissionSettings,
        ApprovalStreak,
        ActionLogEntry,
        Example,
        CalibrationJob,
    ]
    await init_beanie(database=db, document_models=document_models, allow_index_dropping=True)
    # Clear documents instead of dropping the database: re-creating indexes after
    # a drop takes seconds per collection on slow disks. Clearing at setup also
    # covers data left behind by an aborted run.
    for model in document_models:
        await model.find_all().delete()
    await db["user"].delete_many({})  # Better Auth's owner record, read by the sync engine

    yield db

    await client.close()


@pytest.fixture(scope="function")
async def db_transaction(test_db):
    """Isolated test DB. Isolation comes from test_db clearing every collection
    before each test; a real transaction would need a replica set."""
    yield test_db


@pytest.fixture
def client():
    """Test client signed in as OWNER_ID."""
    with TestClient(app, headers=bearer_headers()) as c:
        yield c


@pytest.fixture
async def async_client():
    """Create an async test client for route tests."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
        headers=bearer_headers(),
    ) as client:
        yield client


@pytest.fixture(autouse=True)
def no_paid_ai_outside_integration_tests(request, monkeypatch):
    """A test that reaches the real provider by mistake fails here as it would in CI, instead of quietly
    making a paid call with the developer's key."""
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider_for.cache_clear()  # a client built with the key in an earlier test would still hold it
    yield


# ---------------------
# Mail server (GreenMail, see docker-compose.test.yml)
# ---------------------


@pytest.fixture(scope="session")
def mail_server():
    from tests.utils.mail_server import wait_until_ready

    wait_until_ready()


@pytest.fixture
def mailbox(mail_server):
    """A fresh, empty mailbox on the test mail server."""
    from tests.utils.mail_server import new_mailbox

    return new_mailbox()


# ---------------------
# API stand-ins. They live here rather than in a subdirectory's conftest because pytest 9
# binds a conftest's fixtures to the first node it builds for that directory, and a
# command line that names the directory's files on either side of another file builds a
# second node that can't see them (#175).
# ---------------------


@pytest.fixture
async def plugins(mailbox):
    """The reference IMAP plugin on the owner's GreenMail account, serving the API's mailbox actions."""
    from tests.conformance.test_mailbox_conformance import reference_imap_plugin
    from tests.test_sync.test_inbox_sync import connected

    mailbox.create_folder("Archive")
    async with connected(reference_imap_plugin(mailbox)) as registry:
        app.dependency_overrides[plugin_registry] = lambda: registry
        yield registry
    app.dependency_overrides.pop(plugin_registry, None)


@pytest.fixture
def ai():
    provider = FakeAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider)
