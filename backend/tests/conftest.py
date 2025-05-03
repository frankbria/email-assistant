# backend/tests/conftest.py

import os
import sys


# Ensure imports resolve properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import asyncio
import pytest
import httpx
from dotenv import load_dotenv
from unittest.mock import patch
from beanie import init_beanie
from motor import motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.testclient import TestClient


# App imports
from app.main import app
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.webhook_security import WebhookSecurity
from app.models.user_settings import UserSettings
from app.config import get_settings, Settings
from app.strategies.action_registry import ActionRegistry
import json
from tests.utils.fakes import mock_openai_response, async_return
from tests.utils.openai_mocks import (
    make_mock_openai_response,
    always_raise_openai_error,
)

# Load environment variables
load_dotenv()

# Set test environment variables (override as needed)
os.environ["MONGODB_URI"] = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
os.environ["MONGODB_DB"] = os.getenv("MONGODB_TEST_DB", "email_assistant_test")
os.environ["USE_AI_CONTEXT"] = "false"
os.environ["USE_AI_SUMMARY"] = "false"
os.environ["OPENAI_API_KEY"] = "test_key"
os.environ["OPENAI_API_MODEL"] = "gpt-3-5-turbo"

# ---------------------
# Core Fixtures
# ---------------------


@pytest.fixture(scope="function")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()

    # add debugging capabilities to the loop
    loop.set_debug(True)

    asyncio.set_event_loop(loop)
    print(f"Created event loop with id: {id(loop)}")

    yield loop

    print(f"Checking loop status with id: {id(loop)}")
    # Close the loop after all tests complete
    if not loop.is_closed():
        pending = asyncio.all_tasks(loop=loop)
        if pending:
            print(f"Canceling {len(pending)} pending tasks before closing the loop")
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

    print(f"Closing event loop with id: {id(loop)}")
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()


@pytest.fixture(scope="function")
async def test_db(event_loop):
    """Initialize test database connection and Beanie."""
    mongo_uri = os.environ["MONGODB_URI"]
    test_db_name = os.environ["MONGODB_DB"]

    print(f"Using test database: {mongo_uri}/{test_db_name}")

    if "_test" not in test_db_name.lower():
        raise ValueError("Test is attempting to use production database! Aborting.")

    client = AsyncIOMotorClient(mongo_uri, io_loop=event_loop)

    db = client[test_db_name]

    await init_beanie(
        database=db,
        document_models=[EmailMessage, AssistantTask, WebhookSecurity, UserSettings],
        allow_index_dropping=True,
    )

    yield db

    await client.drop_database(test_db_name)
    client.close()


@pytest.fixture(scope="function")
async def db_transaction(test_db):
    """Create a transaction for test isolation that's connected to the main event loop."""

    # Start transaction
    session = await test_db.client.start_session()
    session.start_transaction()

    yield session

    # Rollback transaction to reset database state
    await session.abort_transaction()
    await session.end_session()


@pytest.fixture
def client():
    """Create a test client for route tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    """Create an async test client for route tests."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        yield client


# ---------------------
# Auto-loaded test data
# ---------------------


@pytest.fixture
async def set_webhook_security(test_db, db_transaction):
    """Set up a valid webhook security configuration."""
    print("Setting up webhook security configuration")
    # Create a valid WebhookSecurity object
    config = WebhookSecurity(api_key="validkey", allowed_ips=["127.0.0.1"], active=True)

    try:
        # Insert the configuration into the database
        await config.insert(session=db_transaction)
        print("Webhook security configuration inserted successfully")
    except Exception as e:
        print(f"Error inserting webhook security configuration: {e}")
        raise e

    yield config

    print("Cleaning up webhook security configuration")


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

    webhook = WebhookSecurity(
        api_key="test_key",
        allowed_ips=["127.0.0.1"],
        active=True,
    )
    await webhook.insert()

    yield

    # No need to clean up test data; each test runs in its own transaction
    # await EmailMessage.find_all().delete()
    # await AssistantTask.find_all().delete()
    # await WebhookSecurity.find_all().delete()


# ---------------------
# AI + Mock Fixtures
# ---------------------


@pytest.fixture
def mock_openai_success_scenario(monkeypatch):
    """Mock OpenAI client to always return a successful response."""
    import json

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
