"""Agent service's own direct MongoDB connection.

Read-only (by convention — the repository functions used here never write)
for shared academic/student collections; full read/write for the agent's
own collections. See `services/agent/app/config.py` module docstring.
"""

from urllib.parse import urlparse

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_mongo_client: AsyncIOMotorClient | None = None
_test_database_override: AsyncIOMotorDatabase | None = None


def set_test_database(database: AsyncIOMotorDatabase | None) -> None:
    global _test_database_override
    _test_database_override = database


def get_mongo_client() -> AsyncIOMotorClient | None:
    global _mongo_client

    settings = get_settings()
    if not settings.mongo_uri:
        return None

    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=2000,
        )

    return _mongo_client


def resolve_database_name(mongo_uri: str) -> str:
    parsed = urlparse(mongo_uri)
    database_name = parsed.path.lstrip("/").split("?")[0]
    return database_name or "unipilot_python"


async def get_database() -> AsyncIOMotorDatabase:
    if _test_database_override is not None:
        return _test_database_override

    settings = get_settings()
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is required")

    client = get_mongo_client()
    if client is None:
        raise RuntimeError("MONGO_URI is required")

    return client[resolve_database_name(settings.mongo_uri)]


async def check_mongo_connectivity() -> str:
    settings = get_settings()
    if not settings.mongo_uri:
        return "not_configured"

    client = get_mongo_client()
    if client is None:
        return "not_configured"

    try:
        await client.admin.command("ping")
        return "connected"
    except Exception:
        return "disconnected"


def close_mongo_client() -> None:
    global _mongo_client

    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
