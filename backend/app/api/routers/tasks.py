# backend/app/api/routers/tasks.py

from fastapi import APIRouter, Depends
from typing import List
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("/", response_model=List[AssistantTask])
async def get_tasks():
    tasks = await AssistantTask.find_all().to_list()
    return tasks  # done!
