# backend/scripts/migrate_user_id.py

import asyncio
import os
import sys
import logging
from typing import List, Dict, Any

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


async def migrate_email_messages_direct(
    client, db_name, default_user_id: str
) -> Dict[str, Any]:
    """
    Migrate all EmailMessage documents that don't have a user_id
    by using direct collection update to bypass validation completely.

    Args:
        client: MongoDB client
        db_name: Database name
        default_user_id: Default user ID to assign

    Returns:
        Dict with migration statistics
    """
    # Get the raw collection
    collection = client[db_name]["email_messages"]

    # Find all document IDs without a user_id
    query = {"user_id": {"$exists": False}}
    cursor = collection.find(query, {"_id": 1})

    # Convert cursor to list of document IDs
    docs = await cursor.to_list(length=None)
    total_emails = len(docs)

    logger.info(f"Found {total_emails} EmailMessage documents without user_id")

    if total_emails == 0:
        return {"total": 0, "updated": 0}

    # Update documents in batches directly
    batch_size = 100
    updated_count = 0

    for i in range(0, total_emails, batch_size):
        batch_ids = [doc["_id"] for doc in docs[i : i + batch_size]]

        # Update documents with user_id without triggering validation
        result = await collection.update_many(
            {"_id": {"$in": batch_ids}}, {"$set": {"user_id": default_user_id}}
        )

        updated_count += result.modified_count
        logger.info(f"Updated {updated_count}/{total_emails} EmailMessage documents")

    return {"total": total_emails, "updated": updated_count}


async def migrate_assistant_tasks_direct(
    client, db_name, default_user_id: str
) -> Dict[str, Any]:
    """
    Migrate all AssistantTask documents that don't have a user_id
    by using direct collection update to bypass validation completely.

    Args:
        client: MongoDB client
        db_name: Database name
        default_user_id: Default user ID to assign

    Returns:
        Dict with migration statistics
    """
    # Get the raw collection
    collection = client[db_name]["assistant_tasks"]

    # Find all document IDs without a user_id
    query = {"user_id": {"$exists": False}}
    cursor = collection.find(query, {"_id": 1})

    # Convert cursor to list of document IDs
    docs = await cursor.to_list(length=None)
    total_tasks = len(docs)

    logger.info(f"Found {total_tasks} AssistantTask documents without user_id")

    if total_tasks == 0:
        return {"total": 0, "updated": 0}

    # Update documents in batches directly
    batch_size = 100
    updated_count = 0

    for i in range(0, total_tasks, batch_size):
        batch_ids = [doc["_id"] for doc in docs[i : i + batch_size]]

        # Update documents with user_id without triggering validation
        result = await collection.update_many(
            {
                "_id": {"$in": batch_ids},
                "email.user_id": {"$exists": False},
            },
            {
                "$set": {
                    "user_id": default_user_id,
                    "email.user_id": default_user_id,
                }
            },
        )

        updated_count += result.modified_count
        logger.info(f"Updated {updated_count}/{total_tasks} AssistantTask documents")

    return {"total": total_tasks, "updated": updated_count}


async def validate_migration() -> Dict[str, int]:
    """
    Validate that all documents have a user_id after migration

    Returns:
        Dict with validation statistics
    """
    emails_without_user_id = await EmailMessage.find(
        {"user_id": {"$exists": False}}
    ).count()

    tasks_without_user_id = await AssistantTask.find(
        {"user_id": {"$exists": False}}
    ).count()

    return {
        "emails_missing_user_id": emails_without_user_id,
        "tasks_missing_user_id": tasks_without_user_id,
    }


async def main():
    """
    Main migration function
    """
    # Initialize database connection
    settings = get_settings()
    mongo_uri = settings.current_mongodb_uri
    db_name = settings.current_mongodb_db

    logger.info(f"Connecting to database: {db_name} at {mongo_uri}")
    client = AsyncIOMotorClient(mongo_uri)

    # Initialize Beanie with the document models (for validation only)
    logger.info("Initializing Beanie ORM")
    await init_beanie(
        database=client[db_name], document_models=[EmailMessage, AssistantTask]
    )

    # Get the default user_id from settings
    default_user_id = settings.DEFAULT_USER_ID
    logger.info(f"Using default user_id: {default_user_id}")

    try:
        # Migrate EmailMessage documents using direct collection access
        logger.info("Starting EmailMessage migration")
        email_stats = await migrate_email_messages_direct(
            client, db_name, default_user_id
        )

        # Migrate AssistantTask documents using direct collection access
        logger.info("Starting AssistantTask migration")
        task_stats = await migrate_assistant_tasks_direct(
            client, db_name, default_user_id
        )

        # Validate migration
        logger.info("Validating migration")
        validation = await validate_migration()

        # Print summary
        logger.info("Migration completed!")
        logger.info(f"EmailMessage stats: {email_stats}")
        logger.info(f"AssistantTask stats: {task_stats}")
        logger.info(f"Validation: {validation}")

        if (
            validation["emails_missing_user_id"] > 0
            or validation["tasks_missing_user_id"] > 0
        ):
            logger.warning(
                "Some documents still don't have a user_id! Migration incomplete."
            )
            return 1
        else:
            logger.info("All documents now have a user_id. Migration successful!")
            return 0

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return 1
    finally:
        # Close the database connection
        client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
