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

    # new flag for AI summarization
    use_ai_summary: bool = False

    # CORS settings
    allow_origins: List[str] = [
        os.getenv("FRONTEND_ORIGIN"),
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

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
