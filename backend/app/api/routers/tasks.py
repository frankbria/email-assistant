# backend/app/api/routers/tasks.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId
from pydantic import BaseModel, Field
import app.services.context_classifier as context_classifier
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskUpdate(BaseModel):
    status: str = Field(
        ...,
        description="New status for the task (e.g., 'done', 'in_progress', 'pending')",
    )
    action_taken: Optional[str] = Field(
        None,
        description="The action that was taken to complete this task",
    )


@router.get("/")
async def get_tasks():
    # Fetch all non-done tasks with their associated emails
    logger.debug("🔄 Fetching active tasks")
    tasks = await AssistantTask.find(AssistantTask.status != "done").to_list()

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
        logger.debug(f"🔄 Updating task {task_id} to status: {update.status}")

        # Convert string ID to ObjectId and find task
        task = await AssistantTask.get(PydanticObjectId(task_id))
        if not task:
            logger.error(f"❌ Task {task_id} not found")
            raise HTTPException(status_code=404, detail="Task not found")

        # Validate status
        valid_statuses = ["pending", "in_progress", "done", "archived"]
        if update.status not in valid_statuses:
            logger.error(f"❌ Invalid status {update.status} for task {task_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
            )

        # Update the task status and action_taken
        task.status = update.status
        if update.status == "done" and update.action_taken:
            task.action_taken = update.action_taken
        await task.save()

        logger.info(
            f"✅ Task {task_id} updated to status: {update.status} with action: {update.action_taken}"
        )
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating task {task_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Internal server error while updating task"
        )
