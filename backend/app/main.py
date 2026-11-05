# backend/app/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.models.user_settings import UserSettings
from app.models.job import Job
from app.models.action_log import ActionLogEntry
from app.models.message import Message
from app.models.ai_usage import AiUsage
from app.models.rule import Rule
from app.models.example import Example
from app.models.calibration import CalibrationJob
from app.permissions import ApprovalStreak, PermissionSettings
from app.models.sync_cursor import SyncCursor
from beanie import init_beanie
from app.api.routers import calibration, connections, filtered, history, jobs, permissions, settings
from app.middleware import setup_cors
from app.config import get_settings, Settings
from pymongo import AsyncMongoClient
from pathlib import Path
from app.plugins.config import load_plugins_config
from app.plugins.registry import PluginRegistry
from app.services.ai_provider import get_ai_provider
from app.sync import SyncEngine
import logging
import asyncio
import os
from datetime import UTC

# Configure logging manually
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)
logger.info("Logger initialized. Log level is %s", LOG_LEVEL)

PLUGIN_SHUTDOWN_SECONDS = 30  # plugins close concurrently, each within 10 s; this bounds a stuck task


async def init_db(settings: Settings | None = None):
    """Initialize database connection"""
    if settings is None:
        settings = get_settings()

    logger.debug(f"🔑 Using MongoDB URI: {settings.current_mongodb_uri}")

    # ponytail: TLS for Atlas (mongodb+srv) only; plain mongodb:// (local/test)
    # connects without it. Self-hosted TLS can opt in via ?tls=true in the URI.
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(
        settings.current_mongodb_uri,
        serverSelectionTimeoutMS=5000,
        socketTimeoutMS=5000,
        connectTimeoutMS=5000,
        tls=settings.current_mongodb_uri.startswith("mongodb+srv://"),
        tz_aware=True,  # naive datetimes reach the API without an offset and browsers read them as local time
        tzinfo=UTC,
    )
    await init_beanie(
        database=client[settings.current_mongodb_db],
        document_models=[
            UserSettings,
            Message,
            Job,
            SyncCursor,
            Rule,
            AiUsage,
            PermissionSettings,
            ApprovalStreak,
            ActionLogEntry,
            Example,
            CalibrationJob,
        ],
        allow_index_dropping=True,
    )

    logger.debug(f"✅ Connecting to DB: {settings.current_mongodb_uri}")
    logger.debug(f"🧠 Using database: {settings.current_mongodb_db}")
    logger.debug(f"Collections: {await client[settings.current_mongodb_db].list_collection_names()}")

    logger.debug("✅ Successfully initialized Beanie")

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.debug("🔄 Starting lifespan")
    settings = get_settings()
    client = await init_db(settings)
    logger.debug("✅ Successfully initialized DB")

    app.state.mongo_client = client
    app.state.settings = settings
    logger.debug("🌟 Lifespan: DB client assigned to app.state")

    # An invalid plugins.yaml (e.g. an inline secret) stops startup; a plugin that
    # can't connect is only recorded as failed.
    plugins = PluginRegistry()
    ready = asyncio.Event()
    plugin_task = asyncio.create_task(plugins.run(load_plugins_config(Path(os.getenv("PLUGINS_CONFIG", "plugins.yaml"))), ready))
    sync_task: asyncio.Task[None] | None = None
    try:
        await ready.wait()
        if plugin_task.done():
            raise RuntimeError("Plugins failed to start; the error is logged below")
        app.state.plugins = plugins
        sync = SyncEngine(
            plugins,
            client[settings.current_mongodb_db]["user"],
            settings.sync_poll_seconds,
            settings.first_connect_days,
            ai_provider_for=get_ai_provider,
            ai_monthly_cap=settings.ai_monthly_cap,
            permissions_file=Path(settings.permissions_file),
        )
        app.state.sync = sync  # the settings API wakes it when the poll interval changes
        sync_task = asyncio.create_task(sync.run())
        yield
    finally:
        if sync_task is not None:  # stop syncing before its plugins close
            sync_task.cancel()
            await asyncio.wait({sync_task})
        plugin_task.cancel()
        await asyncio.wait({plugin_task}, timeout=PLUGIN_SHUTDOWN_SECONDS)
        if not plugin_task.done():
            logger.error("Plugins did not close within %s s", PLUGIN_SHUTDOWN_SECONDS)
        elif not plugin_task.cancelled() and plugin_task.exception() is not None:
            logger.error("Plugin task ended with an error", exc_info=plugin_task.exception())
        logger.debug("🌟 Lifespan: Shutting down DB")
        if client is not None:
            try:
                await client.close()
            except Exception:
                logger.exception("DB client did not close cleanly")


app = FastAPI(title="Email Assistant API", lifespan=lifespan)

# Setup CORS middleware
setup_cors(app)

# Include routers
app.include_router(jobs.router)
app.include_router(history.router)
app.include_router(filtered.router)
app.include_router(settings.router)  # router already has prefix in its definition
app.include_router(connections.router)
app.include_router(permissions.router)
app.include_router(calibration.router)


@app.get("/")
async def read_root():
    return {"message": "Welcome to Email Assistant API"}
