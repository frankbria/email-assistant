# backend/app/middleware.py

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
    # Get allowed origins from environment variable, defaulting to localhost:3200
    allowed_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3200").split(",")
    allowed_credentials = True

    logger.debug(f"🔒 CORS allowed origins: {allowed_origins}")
    print(f"🔒 CORS allowed origins: {allowed_origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allowed_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
