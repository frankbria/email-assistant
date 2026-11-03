# backend/tests/conftest.py

import os
import sys


# Ensure imports resolve properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest
import httpx
from dotenv import load_dotenv
from beanie import init_beanie
from pymongo import AsyncMongoClient
from fastapi.testclient import TestClient


# App imports
from app.main import app
from app.models.user_settings import UserSettings
from app.models.job import Job
from app.models.message import Message
from app.models.ai_usage import AiUsage
from app.models.rule import Rule
from app.permissions import ApprovalStreak, PermissionSettings
from app.models.sync_cursor import SyncCursor
from tests.utils.auth import AUTH_BASE_URL, bearer_headers

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
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(mongo_uri)

    db = client[test_db_name]

    document_models = [UserSettings, Message, Job, SyncCursor, Rule, AiUsage, PermissionSettings, ApprovalStreak]
    await init_beanie(
        database=db, document_models=document_models, allow_index_dropping=True
    )
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
