# tests/conftest.py
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from app.main import app, init_db
import asyncio
import httpx


@pytest.fixture
def client():
    # Ensure Beanie is initialized before tests
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    # Initialize the database for async tests
    await init_db()
    # Use ASGITransport for async client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
