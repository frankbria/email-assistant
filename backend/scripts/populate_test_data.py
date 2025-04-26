# backend/app/scripts/populate_test_data.py

import asyncio
import os
from dotenv import load_dotenv
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.email_task_mapper import map_email_to_task
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import random

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


async def populate_default(num_emails):
    base_emails = [
        EmailMessage(
            sender="bob@example.com",
            subject="Quarterly report due",
            body="Please submit by Friday.",
        ),
        EmailMessage(
            sender="carol@example.com",
            subject="Travel booking needed",
            body="Can you book my flight to NYC?",
        ),
        EmailMessage(
            sender="dave@example.com",
            subject="Lunch meeting follow-up",
            body="About our lunch...",
        ),
        EmailMessage(
            sender="finance@example.com",
            subject="Expense reimbursement",
            body="Please send receipts.",
        ),
        EmailMessage(
            sender="it-support@example.com",
            subject="Laptop won't turn on",
            body="Need help ASAP.",
        ),
        EmailMessage(
            sender="spouse@example.com",
            subject="Birthday gift ideas",
            body="Any suggestions?",
        ),
        EmailMessage(
            sender="ops@example.com",
            subject="Urgent: server down",
            body="Production server offline.",
        ),
        EmailMessage(
            sender="sales@example.com",
            subject="Client renewal forms",
            body="Need signed forms.",
        ),
        EmailMessage(
            sender="healthcare@example.com",
            subject="Reminder: dentist appt",
            body="3pm tomorrow.",
        ),
        EmailMessage(
            sender="weirdguy@example.com",
            subject="FWD: RE: URGENT",
            body="Forwarded forwarded email.",
        ),
    ]

    # Pad if needed
    if num_emails > len(base_emails):
        for i in range(len(base_emails), num_emails):
            base_emails.append(
                EmailMessage(
                    sender=f"extra{i}@example.com",
                    subject=f"Generated Email {i}",
                    body=f"This is a generated email body {i}.",
                )
            )
    await EmailMessage.insert_many(base_emails)

    # Create tasks realistically
    for email in base_emails:
        task = await map_email_to_task(email)  # ← use your real production logic
        await task.insert()  # ← manually insert into database (because map_email_to_task doesn't insert)


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

    print(
        f"Database populated with {num_emails} emails/tasks for scenario '{scenario}'."
    )


if __name__ == "__main__":
    asyncio.run(main())
