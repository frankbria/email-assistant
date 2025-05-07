# backend/app/scripts/populate_test_data.py

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.email_task_mapper import map_email_to_task
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import random

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


async def populate_default(num_emails: int = 10):
    # Define test users - will create emails for each test user
    test_users = ["default", "demo1", "demo2"]

    # Define base emails as dictionaries
    base_emails = [
        {
            "sender": "bob@example.com",
            "subject": "Quarterly report due",
            "body": "Please submit by Friday.",
        },
        {
            "sender": "carol@example.com",
            "subject": "Travel booking needed",
            "body": "Can you book my flight to NYC?",
        },
        {
            "sender": "dave@example.com",
            "subject": "Lunch meeting follow-up",
            "body": "About our lunch...",
        },
        {
            "sender": "finance@example.com",
            "subject": "Expense reimbursement",
            "body": "Please send receipts.",
        },
        {
            "sender": "it-support@example.com",
            "subject": "Laptop won't turn on",
            "body": "Need help ASAP.",
        },
        {
            "sender": "spouse@example.com",
            "subject": "Birthday gift ideas",
            "body": "Any suggestions?",
        },
        {
            "sender": "ops@example.com",
            "subject": "Urgent: server down",
            "body": "Production server offline.",
        },
        {
            "sender": "sales@example.com",
            "subject": "Client renewal forms",
            "body": "Need signed forms.",
        },
        {
            "sender": "healthcare@example.com",
            "subject": "Reminder: dentist appt",
            "body": "3pm tomorrow.",
        },
        {
            "sender": "weirdguy@example.com",
            "subject": "FWD: RE: URGENT",
            "body": "Forwarded forwarded email.",
        },
    ]

    # Pad if more emails are needed
    while len(base_emails) < num_emails:
        i = len(base_emails)
        base_emails.append(
            {
                "sender": f"extra{i}@example.com",
                "subject": f"Generated Email {i}",
                "body": f"This is a generated email body {i}.",
            }
        )

    # Now create emails for each test user
    for user_id in test_users:
        # Convert to EmailMessage documents for this user
        email_objects = [
            EmailMessage(
                sender=email["sender"],
                subject=email["subject"],
                body=email["body"],
                recipient="you@example.com",
                message_id=f"<msg-{user_id}-{i}@example.com>",
                is_spam=random.choice([False, False, True]),
                is_archived=False,
                user_id=user_id,  # Assign user_id to each email
            )
            for i, email in enumerate(base_emails)
        ]

        # Insert into DB
        await EmailMessage.insert_many(email_objects)

        # Map each to a task and insert
        for email in email_objects:
            task = await map_email_to_task(email)
            if task:  # Some emails might be marked as spam and return None
                await task.insert()

        print(f"Created {len(email_objects)} emails for user: {user_id}")


async def main():
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB_URI", "email_assistant")
    client = AsyncIOMotorClient(mongo_uri)
    await init_beanie(
        database=client[db_name], document_models=[EmailMessage, AssistantTask]
    )

    # Clear existing
    await EmailMessage.find_all().delete()
    await AssistantTask.find_all().delete()

    # Scenario selection
    scenario = os.getenv("TEST_DATA_SCENARIO", "default")
    num_emails = int(os.getenv("TEST_DATA_NUM_EMAILS", "10"))

    if scenario == "default":
        await populate_default(num_emails)
    else:
        raise ValueError(f"Unknown TEST_DATA_SCENARIO '{scenario}'")

    total_emails = await EmailMessage.find_all().count()
    total_tasks = await AssistantTask.find_all().count()

    print(
        f"Database populated with {total_emails} total emails and {total_tasks} total tasks for scenario '{scenario}'."
    )


if __name__ == "__main__":
    asyncio.run(main())
