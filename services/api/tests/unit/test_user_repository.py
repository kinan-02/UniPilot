"""Unit tests for user_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.user_repository import (
    create_user,
    find_user_by_email,
    find_user_by_id,
    normalize_email,
    to_public_user,
)


# ---------------------------------------------------------------------------
# normalize_email
# ---------------------------------------------------------------------------

def test_normalize_email_lowercases():
    assert normalize_email("Alice@Example.COM") == "alice@example.com"


def test_normalize_email_strips_whitespace():
    assert normalize_email("  user@test.org  ") == "user@test.org"


def test_normalize_email_already_normalized():
    assert normalize_email("user@test.org") == "user@test.org"


# ---------------------------------------------------------------------------
# to_public_user
# ---------------------------------------------------------------------------

def test_to_public_user_returns_none_for_none():
    assert to_public_user(None) is None


def test_to_public_user_extracts_id_email_created_at():
    oid = ObjectId()
    doc = {
        "_id": oid,
        "email": "user@test.org",
        "passwordHash": "hashed",
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_user(doc)
    assert result is not None
    assert result["id"] == str(oid)
    assert result["email"] == "user@test.org"
    assert result["createdAt"] == "2025-01-01T00:00:00Z"
    assert "passwordHash" not in result


def test_to_public_user_passthrough_non_datetime_created_at():
    oid = ObjectId()
    doc = {
        "_id": oid,
        "email": "user@test.org",
        "passwordHash": "hashed",
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-01T00:00:00Z",
    }
    result = to_public_user(doc)
    assert result is not None
    assert result["createdAt"] == "2025-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_returns_document_with_id(mongo_database):
    result = await create_user(
        mongo_database,
        email="alice@example.com",
        password_hash="hash123",
    )
    assert "_id" in result
    assert result["email"] == "alice@example.com"
    assert result["passwordHash"] == "hash123"
    assert isinstance(result["createdAt"], datetime)


@pytest.mark.asyncio
async def test_create_user_normalizes_email(mongo_database):
    result = await create_user(
        mongo_database,
        email="ALICE@EXAMPLE.COM",
        password_hash="hash123",
    )
    assert result["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_find_user_by_email_returns_user(mongo_database):
    await create_user(mongo_database, email="bob@example.com", password_hash="hash456")
    user = await find_user_by_email(mongo_database, "bob@example.com")
    assert user is not None
    assert user["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_find_user_by_email_is_case_insensitive(mongo_database):
    await create_user(mongo_database, email="bob@example.com", password_hash="hash456")
    user = await find_user_by_email(mongo_database, "BOB@EXAMPLE.COM")
    assert user is not None


@pytest.mark.asyncio
async def test_find_user_by_email_returns_none_for_unknown(mongo_database):
    user = await find_user_by_email(mongo_database, "unknown@example.com")
    assert user is None


@pytest.mark.asyncio
async def test_find_user_by_id_returns_user(mongo_database):
    created = await create_user(
        mongo_database, email="carol@example.com", password_hash="hash789"
    )
    user_id = str(created["_id"])
    user = await find_user_by_id(mongo_database, user_id)
    assert user is not None
    assert user["email"] == "carol@example.com"


@pytest.mark.asyncio
async def test_find_user_by_id_returns_none_for_invalid_id(mongo_database):
    user = await find_user_by_id(mongo_database, "not-an-object-id")
    assert user is None


@pytest.mark.asyncio
async def test_find_user_by_id_returns_none_for_unknown_id(mongo_database):
    user = await find_user_by_id(mongo_database, str(ObjectId()))
    assert user is None
