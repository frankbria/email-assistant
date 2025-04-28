from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
import os
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI application"""
    env = os.getenv("API_ENVIRONMENT", "production")

    # Get allowed origins from environment variable, defaulting to localhost:3000
    if env == "development":
        # Allow all origins in development
        allowed_origins = ["*"]
    else:
        # Allow only the specified origin in production
        allowed_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(
            ","
        )

    logger.debug(f"🔒 CORS allowed origins: {allowed_origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
