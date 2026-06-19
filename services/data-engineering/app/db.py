from urllib.parse import urlparse

from pymongo import MongoClient
from pymongo.database import Database

from app.config import get_settings

_client: MongoClient | None = None
_test_database_override: Database | None = None


def set_test_database(database: Database | None) -> None:
    global _test_database_override
    _test_database_override = database


def resolve_database_name(mongo_uri: str, explicit_name: str) -> str:
    if explicit_name:
        return explicit_name

    parsed = urlparse(mongo_uri)
    database_name = parsed.path.lstrip("/").split("?")[0]
    return database_name or "unipilot_python"


def get_mongo_client() -> MongoClient:
    global _client

    if _client is None:
        settings = get_settings()
        _client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=3000,
        )

    return _client


def get_database() -> Database:
    if _test_database_override is not None:
        return _test_database_override

    settings = get_settings()
    client = get_mongo_client()
    database_name = resolve_database_name(settings.mongo_uri, settings.mongo_db_name)
    return client[database_name]


def check_mongo_connectivity() -> str:
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return "connected"
    except Exception:
        return "disconnected"


def close_mongo_client() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
