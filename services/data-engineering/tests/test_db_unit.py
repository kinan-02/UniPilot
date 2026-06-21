"""Unit tests for app/db.py — all public functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.db import (
    check_mongo_connectivity,
    close_mongo_client,
    get_database,
    get_mongo_client,
    resolve_database_name,
    set_test_database,
)


# ---------------------------------------------------------------------------
# resolve_database_name
# ---------------------------------------------------------------------------

class TestResolveDatabaseName:
    def test_explicit_name_wins(self):
        result = resolve_database_name("mongodb://localhost/ignored", "mydb")
        assert result == "mydb"

    def test_uri_path_used_when_no_explicit_name(self):
        result = resolve_database_name("mongodb://localhost/fromuri", "")
        assert result == "fromuri"

    def test_default_fallback_when_no_path(self):
        result = resolve_database_name("mongodb://localhost/", "")
        assert result == "unipilot_python"

    def test_query_string_stripped_from_uri(self):
        result = resolve_database_name("mongodb://localhost/mydb?authSource=admin", "")
        assert result == "mydb"


# ---------------------------------------------------------------------------
# get_mongo_client (cached singleton)
# ---------------------------------------------------------------------------

class TestGetMongoClient:
    def test_returns_client_instance(self, monkeypatch):
        from app.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("MONGO_URI", "mongodb://localhost/test_client")
        monkeypatch.setenv("MONGO_DB_NAME", "test_client")
        get_settings.cache_clear()

        import app.db as db_module
        db_module._client = None

        with patch("app.db.MongoClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance
            client = get_mongo_client()

        assert client is mock_instance
        db_module._client = None

    def test_reuses_existing_client(self, monkeypatch):
        import app.db as db_module

        sentinel = MagicMock()
        db_module._client = sentinel

        client = get_mongo_client()
        assert client is sentinel
        db_module._client = None


# ---------------------------------------------------------------------------
# get_database
# ---------------------------------------------------------------------------

class TestGetDatabase:
    def test_returns_test_override_when_set(self):
        mock_db = MagicMock()
        set_test_database(mock_db)
        result = get_database()
        assert result is mock_db
        set_test_database(None)

    def test_returns_real_db_when_no_override(self, monkeypatch):
        from app.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("MONGO_URI", "mongodb://localhost/realdb")
        monkeypatch.setenv("MONGO_DB_NAME", "realdb")
        get_settings.cache_clear()

        set_test_database(None)

        import app.db as db_module
        db_module._client = None

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        with patch("app.db.MongoClient", return_value=mock_client):
            result = get_database()

        assert result is mock_db
        db_module._client = None


# ---------------------------------------------------------------------------
# check_mongo_connectivity
# ---------------------------------------------------------------------------

class TestCheckMongoConnectivity:
    def test_connected_when_ping_succeeds(self):
        import app.db as db_module

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}
        db_module._client = mock_client

        result = check_mongo_connectivity()
        assert result == "connected"
        db_module._client = None

    def test_disconnected_when_ping_raises(self):
        import app.db as db_module

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = Exception("timeout")
        db_module._client = mock_client

        result = check_mongo_connectivity()
        assert result == "disconnected"
        db_module._client = None


# ---------------------------------------------------------------------------
# close_mongo_client
# ---------------------------------------------------------------------------

class TestCloseMongoClient:
    def test_closes_existing_client(self):
        import app.db as db_module

        mock_client = MagicMock()
        db_module._client = mock_client

        close_mongo_client()

        mock_client.close.assert_called_once()
        assert db_module._client is None

    def test_safe_when_no_client(self):
        import app.db as db_module

        db_module._client = None
        close_mongo_client()
        assert db_module._client is None

    def test_idempotent_double_close(self):
        import app.db as db_module

        mock_client = MagicMock()
        db_module._client = mock_client

        close_mongo_client()
        close_mongo_client()

        mock_client.close.assert_called_once()
