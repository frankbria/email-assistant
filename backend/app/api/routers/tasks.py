# backend/app/api/routers/tasks.py

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Optional
from app.models.assistant_task import AssistantTask
from beanie import PydanticObjectId
from beanie.operators import Eq
from pydantic import BaseModel, Field
import app.services.context_classifier as context_classifier
import logging
from app.utils.user_utils import get_current_user_id

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
async def get_tasks(
    request: Request, status: str = "active", spam: Optional[bool] = Query(None)
):
    logger.debug("🔄 Fetching active tasks")

    # Get the current user ID
    user_id = await get_current_user_id(request)

    filters = [
        # Filter tasks by the current user_id
        AssistantTask.user_id
        == user_id
    ]

    if status == "active":
        filters.append(AssistantTask.status != "done")
    else:
        filters.append(AssistantTask.status == status)

    if spam is not None:
        filters.append(Eq("email.is_spam", spam))

    query = AssistantTask.find(*filters)

    tasks = await query.to_list()

    for t in tasks:
        if not t.context:
            t.context = await context_classifier.classify_context(
                t.subject or t.email.subject, t.email.body
            )

    return tasks


@router.patch("/{task_id}", response_model=AssistantTask)
async def update_task(task_id: str, update: TaskUpdate, request: Request):
    try:
        logger.debug(f"🔄 Updating task {task_id} to status: {update.status}")

        # Get the current user ID
        user_id = await get_current_user_id(request)

        # Convert string ID to ObjectId and find task, filtering by user_id
        task = await AssistantTask.find_one(
            {"_id": PydanticObjectId(task_id), "user_id": user_id}
        )

        if not task:
            logger.error(f"❌ Task {task_id} not found for user {user_id}")
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
