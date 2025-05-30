# backend/app/main.py

from fastapi import FastAPI, Body, Depends
from contextlib import asynccontextmanager
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.models.user_settings import UserSettings
from app.models.webhook_security import WebhookSecurity
from beanie import init_beanie
import motor.motor_asyncio
from app.api.routers import email, tasks, settings, admin
from app.middleware import setup_cors, limiter, RATE_LIMIT
from app.config import get_settings, Settings
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import uuid
from beanie.exceptions import CollectionWasNotInitialized
from typing import Optional
import logging
import os
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# Configure logging manually
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)
logger.info("Logger initialized. Log level is %s", LOG_LEVEL)


async def init_db(settings: Settings = None):
    """Initialize database connection"""
    if settings is None:
        settings = get_settings()

    logger.debug(f"🔑 Using MongoDB URI: {settings.current_mongodb_uri}")

    client = AsyncIOMotorClient(
        settings.current_mongodb_uri,
        serverSelectionTimeoutMS=5000,
        socketTimeoutMS=5000,
        connectTimeoutMS=5000,
        tls=True,
    )
    await init_beanie(
        database=client[settings.current_mongodb_db],
        document_models=[EmailMessage, AssistantTask, UserSettings, WebhookSecurity],
        allow_index_dropping=True,
    )

    logger.debug(f"✅ Connecting to DB: {settings.current_mongodb_uri}")
    logger.debug(f"🧠 Using database: {settings.current_mongodb_db}")
    logger.debug(
        f"Collections: {await client[settings.current_mongodb_db].list_collection_names()}"
    )

    logger.debug("✅ Successfully initialized Beanie")

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.debug("🔄 Starting lifespan")
    settings = get_settings()
    client = await init_db(settings)
    logger.debug("✅ Successfully initialized DB")

    app.state.motor_client = client
    app.state.settings = settings
    logger.debug("🌟 Lifespan: DB client assigned to app.state")

    # Database setup only in lifespan
    yield

    logger.debug("🌟 Lifespan: Shutting down DB")
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


app = FastAPI(title="Email Assistant API", lifespan=lifespan)

# Configure rate limiting middleware
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup CORS middleware
setup_cors(app)

# Include routers
app.include_router(email.router)  # router already has prefix in its definition
app.include_router(tasks.router)  # router already has prefix in its definition
app.include_router(settings.router)  # router already has prefix in its definition
app.include_router(admin.router)  # admin endpoints for webhook security


@app.get("/")
async def read_root():
    return {"message": "Welcome to Email Assistant API"}


"""
def main():
    import sys
    import subprocess

    if "--populate_db" in sys.argv:
        logger.debug("Populating database...")
        subprocess.run(["python", "scripts/populate_test_data.py"], check=True)
        sys.argv.remove("--populate_db")

    # Start uvicorn programatically
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
"""
