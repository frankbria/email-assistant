# backend/app/main.py

from fastapi import FastAPI, Body
from contextlib import asynccontextmanager
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import init_beanie
import motor.motor_asyncio
import asyncio
from app.api.routers import email
from dotenv import load_dotenv
import os

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "email_assistant")


async def init_db():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    await init_beanie(
        database=client[MONGODB_DB],
        document_models=[EmailMessage, AssistantTask],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(email.router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI with Poetry!"}


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
