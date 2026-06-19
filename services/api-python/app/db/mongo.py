from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings

_mongo_client: AsyncIOMotorClient | None = None


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


async def close_mongo_client() -> None:
    global _mongo_client

    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
