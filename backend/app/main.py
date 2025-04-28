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

    print(f"🔑 Using MongoDB URI: {settings.current_mongodb_uri}")

    client = AsyncIOMotorClient(
        settings.current_mongodb_uri,
        serverSelectionTimeoutMS=5000,
        socketTimeoutMS=5000,
        connectTimeoutMS=5000,
        tls=True,
    )
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

    print("✅ Successfully initialized Beanie")

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 Starting lifespan")
    settings = get_settings()
    client = await init_db(settings)
    print("✅ Successfully initialized DB")

    app.state.motor_client = client
    app.state.settings = settings
    print("🌟 Lifespan: DB client assigned to app.state")
    yield

    print("🌟 Lifespan: Shutting down DB")
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


def main():
    import sys
    import subprocess

    if "--populate_db" in sys.argv:
        print("Populating database...")
        subprocess.run(["python", "scripts/populate_test_data.py"], check=True)
        sys.argv.remove("--populate_db")

    # Start uvicorn programatically
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
