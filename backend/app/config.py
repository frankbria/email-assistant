# backend/app/config.py

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List
import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""

    # MongoDB connection settings
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "email_assistant")

    # Test database settings
    mongodb_test_uri: str = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
    mongodb_test_db: str = os.getenv("MONGODB_TEST_DB", "email_assistant_test")

    # API settings
    api_environment: str = os.getenv(
        "API_ENVIRONMENT", "test" if "pytest" in sys.modules else "development"
    )

    # User settings
    DEFAULT_USER_ID: str = os.getenv("DEFAULT_USER_ID", "default")

    # email settings
    duplicate_threshold: float = os.getenv("DUPLICATE_THRESHOLD", 0.9)

    # new flag for AI summarization
    use_ai_summary: bool = False

    # new flag for AI action suggestions
    use_ai_actions: bool = False

    # CORS settings
    allow_origins: List[str] = [
        os.getenv("FRONTEND_ORIGIN"),
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # === Email box provider information ===
    mailbox_domain: str = os.getenv("MAILBOX_DOMAIN", "mailslurp.biz")
    mailbox_api_key: str = os.getenv(
        "MAILBOX_API_KEY",
        "s84794f37f7397a0f949013cf16d2c215cad5ef7921137fc704fe1f03fd72f3e8",
    )

    # === Temporary IMAP for mailslurp (before webhook is implemented) ===
    imap_host: str = os.getenv("IMAP_HOST", "mailslurpimap.click")
    imap_port: int = os.getenv("IMAP_PORT", 8993)
    imap_username: str = os.getenv(
        "IMAP_USERNAME", "34191648-da63-4666-b0aa-e66014f93069@mailslurp.biz"
    )
    imap_password: str = os.getenv("IMAP_PASSWORD", "ZGtKVswk55EIUVmV1UVQ4umFDum8wmNq")

    emergency_webhook_api_key: str = os.getenv("EMERGENCY_WEBHOOK_API_KEY")

    @property
    def is_test(self) -> bool:
        """Check if running in test environment"""
        return self.api_environment.lower() == "test"

    @property
    def current_mongodb_uri(self) -> str:
        """Get the current MongoDB URI based on environment"""
        return self.mongodb_test_uri if self.is_test else self.mongodb_uri

    @property
    def current_mongodb_db(self) -> str:
        """Get the current MongoDB database name based on environment"""
        return self.mongodb_test_db if self.is_test else self.mongodb_db

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
