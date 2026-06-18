# backend/app/middleware.py

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
import os
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Rate limiter setup
RATE_LIMIT = os.getenv("WEBHOOK_RATE_LIMIT", "5/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI application"""
    # Get allowed origins from environment variable, defaulting to localhost:3000
    allowed_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
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
