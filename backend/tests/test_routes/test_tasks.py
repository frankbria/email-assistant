# backend/tests/test_routes/test_tasks.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from beanie import init_beanie
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_get_tasks(client):
    """Test that GET /api/tasks returns a list of tasks"""
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    task = data[0]
    assert "email" in task
    assert "subject" in task["email"]
    assert "sender" in task["email"]
    assert "body" in task["email"]
    assert "context" in task
    assert "summary" in task
    assert "suggested_actions" in task
    assert "status" in task
