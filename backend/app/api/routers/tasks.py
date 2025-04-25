# backend/app/api/routers/tasks.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskUpdate(BaseModel):
    status: str


@router.get("/", response_model=List[AssistantTask])
async def get_tasks():
    tasks = await AssistantTask.find_all().to_list()
    return tasks  # done!


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
