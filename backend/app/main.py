# backend/app/main.py

from fastapi import FastAPI, Body
from contextlib import asynccontextmanager
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import init_beanie
import motor.motor_asyncio
import asyncio
from app.api.routers import email, tasks
from app.middleware import setup_cors
from dotenv import load_dotenv
import os
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
MONGODB_URI = os.getenv(
    "MONGODB_URI", "mongodb://localhost:27017"
)  # Default to local MongoDB
MONGODB_DB = os.getenv("MONGODB_DB", "email_assistant")


async def init_db():
    """Initialize database connection"""
    client = AsyncIOMotorClient(MONGODB_URI)
    await init_beanie(
        database=client[MONGODB_DB],
        document_models=[EmailMessage, AssistantTask],
    )
    print("✅ Connecting to DB:", client.list_database_names())
    print("🧠 Using database:", MONGODB_DB)

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await init_db()
    app.state.motor_client = client
    yield
    client.close()


app = FastAPI(title="Email Assistant API", lifespan=lifespan)

# Setup CORS middleware
setup_cors(app)

# Include routers
app.include_router(email.router)  # router already has prefix in its definition
app.include_router(tasks.router)  # router already has prefix in its definition


@app.get("/")
async def read_root():
    return {"message": "Welcome to Email Assistant API"}


@app.post("/api/v1/email")
async def create_email_task(
    sender: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
):
    email = EmailMessage(subject=subject, sender=sender, body=body)
    await email.insert()
    task = AssistantTask(email=email)
    await task.insert()
    return {"email_id": str(email.id), "task_id": str(task.id)}
