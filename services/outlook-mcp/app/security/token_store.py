"""Encrypted per-user Microsoft Graph OAuth token storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.security.token_crypto import TokenCryptoError, decrypt_secret, encrypt_secret

OUTLOOK_TOKENS_COLLECTION = "outlook_oauth_tokens"


async def ensure_outlook_token_indexes(database: AsyncIOMotorDatabase) -> None:
    await database[OUTLOOK_TOKENS_COLLECTION].create_index(
        [("userId", 1)],
        unique=True,
        name="outlook_tokens_unique_user",
    )


async def upsert_outlook_tokens(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    microsoft_user_id: str,
    email: str,
    access_token: str,
    refresh_token: str,
    access_token_expires_at: datetime,
    scopes: list[str],
) -> None:
    settings = get_settings()
    raw_key = settings.require_token_encryption_key()
    now = datetime.now(timezone.utc)

    document: dict[str, Any] = {
        "userId": ObjectId(user_id),
        "microsoftUserId": microsoft_user_id,
        "email": email.strip().lower(),
        "encryptedAccessToken": encrypt_secret(access_token, raw_key=raw_key),
        "encryptedRefreshToken": encrypt_secret(refresh_token, raw_key=raw_key),
        "accessTokenExpiresAt": access_token_expires_at,
        "scopes": scopes,
        "updatedAt": now,
    }

    await database[OUTLOOK_TOKENS_COLLECTION].update_one(
        {"userId": ObjectId(user_id)},
        {"$set": document, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )


async def find_outlook_tokens_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any] | None:
    try:
        parsed_user_id = ObjectId(user_id)
    except Exception:
        return None

    return await database[OUTLOOK_TOKENS_COLLECTION].find_one({"userId": parsed_user_id})


async def delete_outlook_tokens(database: AsyncIOMotorDatabase, user_id: str) -> bool:
    try:
        parsed_user_id = ObjectId(user_id)
    except Exception:
        return False

    result = await database[OUTLOOK_TOKENS_COLLECTION].delete_one({"userId": parsed_user_id})
    return result.deleted_count > 0


def decrypt_access_token(document: dict[str, Any]) -> str:
    settings = get_settings()
    raw_key = settings.require_token_encryption_key()
    ciphertext = document.get("encryptedAccessToken")
    if not isinstance(ciphertext, str) or not ciphertext:
        raise TokenCryptoError("Missing access token")
    return decrypt_secret(ciphertext, raw_key=raw_key)


def decrypt_refresh_token(document: dict[str, Any]) -> str:
    settings = get_settings()
    raw_key = settings.require_token_encryption_key()
    ciphertext = document.get("encryptedRefreshToken")
    if not isinstance(ciphertext, str) or not ciphertext:
        raise TokenCryptoError("Missing refresh token")
    return decrypt_secret(ciphertext, raw_key=raw_key)


async def update_access_token(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    access_token: str,
    access_token_expires_at: datetime,
    refresh_token: str | None = None,
) -> None:
    settings = get_settings()
    raw_key = settings.require_token_encryption_key()
    update_fields: dict[str, Any] = {
        "encryptedAccessToken": encrypt_secret(access_token, raw_key=raw_key),
        "accessTokenExpiresAt": access_token_expires_at,
        "updatedAt": datetime.now(timezone.utc),
    }
    if refresh_token is not None:
        update_fields["encryptedRefreshToken"] = encrypt_secret(refresh_token, raw_key=raw_key)

    await database[OUTLOOK_TOKENS_COLLECTION].update_one(
        {"userId": ObjectId(user_id)},
        {"$set": update_fields},
    )
