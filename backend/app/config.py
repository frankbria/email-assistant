# backend/app/config.py

from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
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

    # Better Auth (the Next.js app): JWT issuer/audience, and where its JWKS lives.
    # BETTER_AUTH_JWKS_URL overrides the JWKS location, e.g. an internal Docker address.
    better_auth_url: str = "http://localhost:3000"
    better_auth_jwks_url_override: str | None = Field(default=None, alias="BETTER_AUTH_JWKS_URL")

    # AI provider (env AI_PROVIDER / AI_MODEL); the Anthropic key is ANTHROPIC_API_KEY.
    ai_provider: str = "anthropic"
    ai_model: str = "claude-opus-5-5"

    # new flag for AI summarization
    use_ai_summary: bool = False

    # new flag for AI action suggestions
    use_ai_actions: bool = False

    # CORS settings
    allow_origins: List[str] = [
        origin
        for origin in [
            os.getenv("FRONTEND_ORIGIN"),
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:8000",
        ]
        if origin
    ]

    @property
    def better_auth_jwks_url(self) -> str:
        return self.better_auth_jwks_url_override or f"{self.better_auth_url}/api/auth/jwks"

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
