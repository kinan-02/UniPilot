"""MongoDB access for MAS user data and session persistence."""

from __future__ import annotations

from urllib.parse import urlparse

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_mongo_client: AsyncIOMotorClient | None = None


def resolve_database_name(mongo_uri: str) -> str:
    parsed = urlparse(mongo_uri)
    database_name = parsed.path.lstrip("/").split("?")[0]
    return database_name or "unipilot_python"


def get_mongo_client() -> AsyncIOMotorClient | None:
    global _mongo_client

    settings = get_settings()
    if not settings.mongo_uri:
        return None

    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5000,
        )
    return _mongo_client


async def get_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is required for MAS")

    client = get_mongo_client()
    if client is None:
        raise RuntimeError("MONGO_URI is required for MAS")

    return client[resolve_database_name(settings.mongo_uri)]


def close_mongo_client() -> None:
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
