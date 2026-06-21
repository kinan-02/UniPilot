"""Unit tests for app/db/mongo.py — covers the uncovered branches."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mongomock_motor import AsyncMongoMockClient

from app.db.mongo import (
    check_mongo_connectivity,
    close_mongo_client,
    get_database,
    get_mongo_client,
    resolve_database_name,
    set_test_database,
)


# ---------------------------------------------------------------------------
# resolve_database_name — lines 33-35
# ---------------------------------------------------------------------------


def test_resolve_database_name_extracts_db_from_uri():
    assert resolve_database_name("mongodb://localhost/mydb") == "mydb"


def test_resolve_database_name_strips_query_params():
    assert resolve_database_name("mongodb://localhost/unipilot_python?authSource=admin") == "unipilot_python"


def test_resolve_database_name_falls_back_to_default_when_path_empty():
    assert resolve_database_name("mongodb://localhost/") == "unipilot_python"


def test_resolve_database_name_handles_uri_without_path():
    result = resolve_database_name("mongodb://localhost")
    assert result == "unipilot_python"


# ---------------------------------------------------------------------------
# get_mongo_client — line 21 (returns None when MONGO_URI is absent)
# ---------------------------------------------------------------------------


def test_get_mongo_client_returns_none_when_no_uri(monkeypatch):
    from app.config import get_settings
    monkeypatch.delenv("MONGO_URI", raising=False)
    get_settings.cache_clear()
    close_mongo_client()
    result = get_mongo_client()
    assert result is None


def test_get_mongo_client_creates_client_when_uri_set(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()
    client = get_mongo_client()
    assert client is not None
    close_mongo_client()


def test_get_mongo_client_returns_same_singleton(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()
    client1 = get_mongo_client()
    client2 = get_mongo_client()
    assert client1 is client2
    close_mongo_client()


def test_close_mongo_client_clears_singleton(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()
    client = get_mongo_client()
    assert client is not None
    close_mongo_client()
    # After closing, next call should create a fresh one (or None if URI cleared)
    # Just verify the old reference is no longer the singleton
    monkeypatch.delenv("MONGO_URI", raising=False)
    get_settings.cache_clear()
    new_client = get_mongo_client()
    assert new_client is None


def test_close_mongo_client_is_idempotent_when_none():
    """close_mongo_client should not raise when called with no active client."""
    close_mongo_client()
    close_mongo_client()  # second call must not raise


# ---------------------------------------------------------------------------
# get_database — lines 42-50
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_database_raises_when_no_uri_and_no_override(monkeypatch):
    from app.config import get_settings
    monkeypatch.delenv("MONGO_URI", raising=False)
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()

    with pytest.raises(RuntimeError, match="MONGO_URI is required"):
        await get_database()


@pytest.mark.asyncio
async def test_get_database_raises_when_client_returns_none(monkeypatch):
    """
    If get_mongo_client() somehow returns None despite MONGO_URI being set
    (defensive branch, lines 47-48), we still raise RuntimeError.
    """
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()

    with patch("app.db.mongo.get_mongo_client", return_value=None):
        with pytest.raises(RuntimeError, match="MONGO_URI is required"):
            await get_database()


@pytest.mark.asyncio
async def test_get_database_returns_correct_db_name(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/mytestdb")
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()

    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)

    with patch("app.db.mongo.get_mongo_client", return_value=mock_client):
        db = await get_database()

    mock_client.__getitem__.assert_called_once_with("mytestdb")
    assert db is mock_db


@pytest.mark.asyncio
async def test_get_database_returns_test_override_when_set():
    mock_db = MagicMock()
    set_test_database(mock_db)
    result = await get_database()
    assert result is mock_db
    set_test_database(None)


# ---------------------------------------------------------------------------
# check_mongo_connectivity — line 60 (client is None) and line 64 (connected)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_mongo_connectivity_returns_not_configured_when_no_uri(monkeypatch):
    from app.config import get_settings
    monkeypatch.delenv("MONGO_URI", raising=False)
    get_settings.cache_clear()
    close_mongo_client()

    result = await check_mongo_connectivity()
    assert result == "not_configured"


@pytest.mark.asyncio
async def test_check_mongo_connectivity_returns_connected_on_successful_ping(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()

    mock_client = MagicMock()
    mock_admin = MagicMock()
    mock_admin.command = AsyncMock(return_value={"ok": 1})
    mock_client.admin = mock_admin

    with patch("app.db.mongo.get_mongo_client", return_value=mock_client):
        result = await check_mongo_connectivity()

    assert result == "connected"


@pytest.mark.asyncio
async def test_check_mongo_connectivity_returns_disconnected_on_ping_failure(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()

    mock_client = MagicMock()
    mock_admin = MagicMock()
    mock_admin.command = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.admin = mock_admin

    with patch("app.db.mongo.get_mongo_client", return_value=mock_client):
        result = await check_mongo_connectivity()

    assert result == "disconnected"


@pytest.mark.asyncio
async def test_check_mongo_connectivity_returns_not_configured_when_client_is_none(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    get_settings.cache_clear()
    close_mongo_client()

    with patch("app.db.mongo.get_mongo_client", return_value=None):
        result = await check_mongo_connectivity()

    assert result == "not_configured"
