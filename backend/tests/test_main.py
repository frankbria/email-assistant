# backend/tests/test_main.py

from fastapi.testclient import TestClient
from app.main import app
import pytest
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask

client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to Email Assistant API"}
