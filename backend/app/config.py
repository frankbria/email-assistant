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
    better_auth_url: str = "http://localhost:3200"
    better_auth_jwks_url_override: str | None = Field(default=None, alias="BETTER_AUTH_JWKS_URL")

    # AI provider (env AI_PROVIDER / AI_MODEL); the Anthropic key is ANTHROPIC_API_KEY.
    ai_provider: str = "anthropic"
    ai_model: str = "claude-opus-5-5"

    # How often each plugin's inbox is polled (env SYNC_POLL_SECONDS); a push polls sooner.
    sync_poll_seconds: float = Field(default=120, gt=0)

    # On first connect only mail from this many recent days is synced (env FIRST_CONNECT_DAYS).
    first_connect_days: int = Field(default=14, gt=0)

    # Optional cap on AI calls per month (env AI_MONTHLY_CAP); unset means no cap. At the cap new mail
    # goes to the owner as ask-owner cards and the app warns once.
    ai_monthly_cap: int | None = Field(default=None, ge=0)

    # The readable per-verb permissions file, kept in sync with the settings screen (env PERMISSIONS_FILE).
    permissions_file: str = "permissions.yaml"

    # CORS settings
    allow_origins: List[str] = [
        origin
        for origin in [
            os.getenv("FRONTEND_ORIGIN"),
            "http://localhost",
            "http://localhost:3200",
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
