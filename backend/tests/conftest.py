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
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.user_settings import UserSettings
from app.config import Settings
from app.strategies.action_registry import ActionRegistry
import json
from tests.utils.fakes import mock_openai_response
from tests.utils.auth import AUTH_BASE_URL, OWNER_ID, bearer_headers

# Load environment variables
load_dotenv()

# Set test environment variables (override as needed)
os.environ["MONGODB_URI"] = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
os.environ["MONGODB_DB"] = os.getenv("MONGODB_TEST_DB", "email_assistant_test")
os.environ["USE_AI_CONTEXT"] = "false"
os.environ["USE_AI_SUMMARY"] = "false"
os.environ["OPENAI_API_KEY"] = "test_key"
os.environ["OPENAI_API_MODEL"] = "gpt-3-5-turbo"

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

    document_models = [EmailMessage, AssistantTask, UserSettings]
    await init_beanie(
        database=db, document_models=document_models, allow_index_dropping=True
    )
    # Clear documents instead of dropping the database: re-creating indexes after
    # a drop takes seconds per collection on slow disks. Clearing at setup also
    # covers data left behind by an aborted run.
    for model in document_models:
        await model.find_all().delete()

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
# Auto-loaded test data
# ---------------------




@pytest.fixture
async def setup_test_data(db_transaction):
    """Populate test DB with basic records for each test."""
    email = EmailMessage(
        subject="Test Email", sender="test@example.com", body="This is a test email"
    )
    await email.insert()

    task = AssistantTask(
        email=email,
        context="test",
        summary="Test task summary",
        actions=["action1", "action2"],
        status="pending",
    )
    await task.insert()

    yield

    # No need to clean up test data; each test runs in its own transaction
    # await EmailMessage.find_all().delete()
    # await AssistantTask.find_all().delete()


# ---------------------
# AI + Mock Fixtures
# ---------------------


@pytest.fixture
def mock_openai_success_scenario(monkeypatch):
    """Mock OpenAI client to always return a successful response."""

    result = {
        "actions": [
            {"label": "Mock Action", "action_type": "mock", "handler": "handle_mock"}
        ]
    }
    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(json.dumps(result)),
    )
    yield


@pytest.fixture
def mock_openai_failure_scenario(monkeypatch):
    """Mock OpenAI client to always raise an exception."""
    monkeypatch.setattr(
        "app.services.action_suggester.openai_client",
        mock_openai_response(exception=Exception("API Error")),
    )
    yield


@pytest.fixture
def mock_context_classifier_scenario(monkeypatch):
    """Mock context classifier to always return a fixed label."""

    async def fake_classify(subject, body):
        return "mocked_context"

    monkeypatch.setattr(
        "app.services.context_classifier.classify_context",
        fake_classify,
    )
    yield


@pytest.fixture
def mock_action_registry_scenario():
    """Clear and register only the mock default strategy."""
    from app.strategies.default import DefaultEmailStrategy

    ActionRegistry._strategies.clear()
    ActionRegistry.register("default", DefaultEmailStrategy)
    yield
    ActionRegistry._strategies.clear()


@pytest.fixture
def mock_settings_scenario(monkeypatch):
    """Mock settings to control AI flags."""

    class MockSettings(Settings):
        use_ai_actions: bool = False
        use_ai_summary: bool = False
        use_ai_context: bool = False
        use_ai_context_classification: bool = False

    monkeypatch.setattr("app.config.get_settings", lambda: MockSettings())
    yield


@pytest.fixture(autouse=True)
def auto_inject_user_id(monkeypatch):
    def wrap_init(orig_init):
        def _init(self, *args, **kwargs):
            # Inject user_id into the constructor
            if "user_id" not in kwargs or kwargs["user_id"] is None:
                kwargs["user_id"] = OWNER_ID
            return orig_init(self, *args, **kwargs)

        return _init

    monkeypatch.setattr(EmailMessage, "__init__", wrap_init(EmailMessage.__init__))
    monkeypatch.setattr(AssistantTask, "__init__", wrap_init(AssistantTask.__init__))
    yield
