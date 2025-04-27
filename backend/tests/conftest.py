# backend/tests/conftest.py
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest
from fastapi.testclient import TestClient
from app.main import app
import asyncio
import httpx
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import init_beanie
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from unittest.mock import patch
from app.config import Settings
from app.strategies.action_registry import ActionRegistry

# Load environment variables
load_dotenv()

# Set test environment variables
os.environ["MONGODB_URI"] = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
os.environ["MONGODB_DB"] = os.getenv("MONGODB_TEST_DB", "email_assistant_test")
os.environ["USE_AI_CONTEXT"] = "false"
os.environ["USE_AI_SUMMARY"] = "false"
os.environ["OPENAI_API_KEY"] = "test_key"
os.environ["OPENAI_API_MODEL"] = "gpt-3-5-turbo"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db():
    """Initialize test database connection"""
    mongo_uri = os.environ["MONGODB_TEST_URI"]
    test_db_name = os.environ["MONGODB_TEST_DB"]
    print(f"Using test database: {mongo_uri}/{test_db_name}")

    # Safety check to prevent production database access
    if "prod" in test_db_name.lower() or "production" in test_db_name.lower():
        raise ValueError("Test is attempting to use production database! Aborting.")

    client = AsyncIOMotorClient(mongo_uri)
    db = client[test_db_name]

    # Initialize Beanie with test database
    await init_beanie(
        database=db,
        document_models=[EmailMessage, AssistantTask],
        allow_index_dropping=True,
    )

    yield db

    # Cleanup
    await client.drop_database(test_db_name)
    client.close()


@pytest.fixture
async def setup_test_data(test_db):
    """Setup test data for each test"""
    # Create test email
    email = EmailMessage(
        subject="Test Email", sender="test@example.com", body="This is a test email"
    )
    await email.insert()

    # Create test task
    task = AssistantTask(
        email=email,
        context="test",
        summary="Test task summary",
        actions=["action1", "action2"],
        status="pending",
    )
    await task.insert()

    yield

    # Cleanup test data
    await EmailMessage.find_all().delete()
    await AssistantTask.find_all().delete()


# The application lifespan already manages database initialisation. Previously we mocked
# `init_db`, however this prevented collections from being registered with Beanie,
# causing `CollectionWasNotInitialized` errors in route tests. The mock has been
# removed so that the real `init_db` executes during tests.


@pytest.fixture
def client(test_db):
    """Create a test client for route tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    """Create an async test client for route tests"""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def disable_ai(monkeypatch):
    """Disable AI features for testing"""

    class MockSettings(Settings):
        use_ai_actions: bool = False
        use_ai_summary: bool = False
        use_ai_context: bool = False
        use_ai_context_classification: bool = False

    monkeypatch.setattr(
        "app.services.action_suggester.get_settings", lambda: MockSettings()
    )
    monkeypatch.setattr(
        "app.services.email_summarizer.get_settings", lambda: MockSettings()
    )
    monkeypatch.setattr("app.config.get_settings", lambda: MockSettings())

    yield  # Nothing to return; just patches


@pytest.fixture(autouse=True, scope="function")
def reset_registry_and_disable_ai(monkeypatch):
    """
    Auto-fixture that:
    - Clears ActionRegistry between tests
    - Forces AI settings OFF unless manually overridden
    """

    # Clear registered strategies
    ActionRegistry._strategies.clear()

    # Force settings to disable AI
    # Force settings to disable AI
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(
            use_ai_summary=False, use_ai_context=False, use_ai_actions=False
        ),
    )

    yield

    # (Optional) re-clear after test (but usually not needed if autouse=True)
    ActionRegistry._strategies.clear()
