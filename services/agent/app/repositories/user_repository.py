from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

USERS_COLLECTION = "users"
AuthProvider = Literal["local", "google"]


def normalize_email(email: str) -> str:
    return str(email).strip().lower()


async def ensure_user_indexes(database: AsyncIOMotorDatabase) -> None:
    await database[USERS_COLLECTION].create_index(
        [("email", 1)],
        unique=True,
        name="users_unique_email",
    )
    await database[USERS_COLLECTION].create_index(
        [("googleId", 1)],
        unique=True,
        sparse=True,
        name="users_unique_google_id",
    )


async def create_user(
    database: AsyncIOMotorDatabase,
    *,
    email: str,
    password_hash: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    user_document = {
        "email": normalize_email(email),
        "passwordHash": password_hash,
        "authProvider": "local",
        "createdAt": now,
        "updatedAt": now,
    }

    insert_result = await database[USERS_COLLECTION].insert_one(user_document)
    return {
        "_id": insert_result.inserted_id,
        **user_document,
    }


async def create_google_user(
    database: AsyncIOMotorDatabase,
    *,
    email: str,
    google_id: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    user_document = {
        "email": normalize_email(email),
        "authProvider": "google",
        "googleId": google_id,
        "createdAt": now,
        "updatedAt": now,
    }

    insert_result = await database[USERS_COLLECTION].insert_one(user_document)
    return {
        "_id": insert_result.inserted_id,
        **user_document,
    }


async def find_user_by_email(database: AsyncIOMotorDatabase, email: str) -> dict[str, Any] | None:
    return await database[USERS_COLLECTION].find_one({"email": normalize_email(email)})


async def find_user_by_google_id(
    database: AsyncIOMotorDatabase,
    google_id: str,
) -> dict[str, Any] | None:
    return await database[USERS_COLLECTION].find_one({"googleId": google_id})


async def find_user_by_id(database: AsyncIOMotorDatabase, user_id: str) -> dict[str, Any] | None:
    try:
        parsed_object_id = ObjectId(str(user_id))
    except Exception:
        return None

    return await database[USERS_COLLECTION].find_one({"_id": parsed_object_id})


def to_public_user(user_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user_document:
        return None

    created_at = user_document["createdAt"]
    if isinstance(created_at, datetime):
        created_at_value = created_at.isoformat().replace("+00:00", "Z")
    else:
        created_at_value = created_at

    return {
        "id": str(user_document["_id"]),
        "email": user_document["email"],
        "authProvider": user_document.get("authProvider", "local"),
        "createdAt": created_at_value,
    }
