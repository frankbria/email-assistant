# backend/app/api/routers/tasks.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId
from pydantic import BaseModel
import app.services.context_classifier as context_classifier

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskUpdate(BaseModel):
    status: str


@router.get("/")
async def get_tasks():
    # Fetch all tasks with their associated emails
    # The model will handle default actions automatically
    tasks = await AssistantTask.find_all().to_list()
    # Fill missing context via classifier using dynamic patchable module
    for t in tasks:
        if not t.context:
            t.context = await context_classifier.classify_context(
                t.subject or t.email.subject, t.email.body
            )
    return tasks


@router.patch("/{task_id}", response_model=AssistantTask)
async def update_task(task_id: str, update: TaskUpdate):
    try:
        # Convert string ID to ObjectId and find task
        task = await AssistantTask.get(PydanticObjectId(task_id))
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update the task status
        task.status = update.status
        await task.save()

        return task
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
