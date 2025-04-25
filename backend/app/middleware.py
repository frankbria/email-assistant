from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI application"""
    # Get allowed origins from environment variable, defaulting to localhost:3000
    allowed_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
