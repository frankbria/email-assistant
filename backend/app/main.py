# backend/app/main.py

from fastapi import FastAPI, Body, Depends
from contextlib import asynccontextmanager
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import init_beanie
import motor.motor_asyncio
from app.api.routers import email, tasks
from app.middleware import setup_cors
from app.config import get_settings, Settings
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import uuid
from beanie.exceptions import CollectionWasNotInitialized
from typing import Optional


async def init_db(settings: Settings = None):
    """Initialize database connection"""
    if settings is None:
        settings = get_settings()

    client = AsyncIOMotorClient(settings.current_mongodb_uri)
    await init_beanie(
        database=client[settings.current_mongodb_db],
        document_models=[EmailMessage, AssistantTask],
        allow_index_dropping=True,
    )
    print(f"✅ Connecting to DB: {settings.current_mongodb_uri}")
    print(f"🧠 Using database: {settings.current_mongodb_db}")
    print(
        f"Collections: {await client[settings.current_mongodb_db].list_collection_names()}"
    )

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = await init_db(settings)
    app.state.motor_client = client
    app.state.settings = settings
    yield
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


app = FastAPI(title="Email Assistant API", lifespan=lifespan)

# Setup CORS middleware
setup_cors(app)

# Include routers
app.include_router(email.router)  # router already has prefix in its definition
app.include_router(tasks.router)  # router already has prefix in its definition


@app.get("/")
async def read_root():
    return {"message": "Welcome to Email Assistant API"}
