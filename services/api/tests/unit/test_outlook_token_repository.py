from datetime import datetime, timezone

import pytest

from app.repositories.outlook_token_repository import (
    delete_outlook_tokens,
    find_outlook_tokens_by_user_id,
    to_public_outlook_status,
    upsert_outlook_tokens,
)
from app.security.token_crypto import TokenCryptoError, decrypt_secret, encrypt_secret


def test_token_crypto_roundtrip():
    raw_key = b"test-outlook-token-encryption-key-32chars"
    encrypted = encrypt_secret("refresh-token-value", raw_key=raw_key)
    assert decrypt_secret(encrypted, raw_key=raw_key) == "refresh-token-value"


def test_token_crypto_invalid_ciphertext():
    raw_key = b"test-outlook-token-encryption-key-32chars"
    with pytest.raises(TokenCryptoError):
        decrypt_secret("not-valid", raw_key=raw_key)


@pytest.mark.asyncio
async def test_outlook_token_repository_crud(mongo_database, monkeypatch):
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
    from app.config import get_settings

    get_settings.cache_clear()

    user_id = "507f1f77bcf86cd799439011"
    assert await find_outlook_tokens_by_user_id(mongo_database, user_id) is None
    assert await find_outlook_tokens_by_user_id(mongo_database, "bad-id") is None

    await upsert_outlook_tokens(
        mongo_database,
        user_id=user_id,
        microsoft_user_id="ms-1",
        email="user@example.com",
        access_token="access",
        refresh_token="refresh",
        access_token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["Mail.Read"],
    )

    stored = await find_outlook_tokens_by_user_id(mongo_database, user_id)
    assert stored is not None
    assert stored["email"] == "user@example.com"
    assert to_public_outlook_status(stored)["connected"] is True
    assert to_public_outlook_status(None)["connected"] is False

    assert await delete_outlook_tokens(mongo_database, user_id) is True
    assert await delete_outlook_tokens(mongo_database, user_id) is False
    assert await delete_outlook_tokens(mongo_database, "bad-id") is False


def test_to_public_outlook_status_handles_non_datetime_updated_at():
    status = to_public_outlook_status({"email": "a@b.com", "updatedAt": "2026-01-01T00:00:00Z"})
    assert status["connected"] is True
    assert status["updatedAt"] == "2026-01-01T00:00:00Z"
