# backend/app/dependencies.py
from fastapi import Request, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient
from app.config import get_settings, Settings


async def get_db(
    request: Request, settings: Settings = Depends(get_settings)
) -> AsyncIOMotorDatabase:
    """
    Get database instance based on the environment.

    If app.state.test_mode is True, return the test database
    stored in app.state.test_db, otherwise return the production database.
    """
    # Check if we're in test mode with a pre-configured test DB
    if hasattr(request.app.state, "test_mode") and request.app.state.test_mode:
        if hasattr(request.app.state, "test_db"):
            return request.app.state.test_db

    # Use the appropriate database based on settings
    client = AsyncIOMotorClient(settings.current_mongodb_uri)
    db = client[settings.current_mongodb_db]

    # Store client in app state to close it later
    if not hasattr(request.app.state, "temp_clients"):
        request.app.state.temp_clients = []
    request.app.state.temp_clients.append(client)

    return db
