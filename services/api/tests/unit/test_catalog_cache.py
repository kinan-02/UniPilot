"""Unit tests for app/services/catalog_cache.py — targets 100% branch coverage."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings, get_settings
import app.services.catalog_cache as cc_module
from app.services.catalog_cache import (
    CATALOG_CACHE_PREFIX,
    course_cache_key,
    degree_programs_cache_key,
    get_cached_json,
    offerings_batch_cache_key,
    set_cached_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dev_settings(**kwargs) -> Settings:
    defaults = dict(
        environment="development",
        jwt_secret="test-secret",
        redis_url="redis://localhost:6379",
        catalog_cache_enabled=True,
    )
    defaults.update(kwargs)
    return Settings(**defaults)


def _patch_settings(monkeypatch, **kwargs):
    s = _dev_settings(**kwargs)
    monkeypatch.setattr(cc_module, "get_settings", lambda: s)
    return s


# ---------------------------------------------------------------------------
# _cache_enabled
# ---------------------------------------------------------------------------


def test_cache_disabled_in_test_environment(monkeypatch) -> None:
    _patch_settings(monkeypatch, environment="test")
    assert cc_module._cache_enabled() is False


def test_cache_disabled_when_redis_url_missing(monkeypatch) -> None:
    _patch_settings(monkeypatch, redis_url=None)
    assert cc_module._cache_enabled() is False


def test_cache_disabled_when_feature_flag_off(monkeypatch) -> None:
    _patch_settings(monkeypatch, catalog_cache_enabled=False)
    assert cc_module._cache_enabled() is False


def test_cache_enabled_in_development_with_redis_url(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    assert cc_module._cache_enabled() is True


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_prepends_prefix() -> None:
    result = cc_module._cache_key("hello")
    assert result == f"{CATALOG_CACHE_PREFIX}hello"


# ---------------------------------------------------------------------------
# get_cached_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cached_json_returns_none_when_cache_disabled(monkeypatch) -> None:
    _patch_settings(monkeypatch, environment="test")
    result = await get_cached_json("some-key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_json_returns_none_when_client_is_none(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: None)
    result = await get_cached_json("some-key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_json_returns_deserialized_data(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    payload = {"id": 1, "name": "test"}
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    result = await get_cached_json("my-suffix")

    assert result == payload
    fake_client.get.assert_awaited_once_with(f"{CATALOG_CACHE_PREFIX}my-suffix")


@pytest.mark.asyncio
async def test_get_cached_json_returns_none_on_cache_miss(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=None)
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    result = await get_cached_json("missing-key")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_json_returns_none_on_redis_exception(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(side_effect=ConnectionError("boom"))
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    result = await get_cached_json("bad-key")
    assert result is None


# ---------------------------------------------------------------------------
# set_cached_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_cached_json_does_nothing_when_cache_disabled(monkeypatch) -> None:
    _patch_settings(monkeypatch, environment="test")
    fake_client = AsyncMock()
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    await set_cached_json("key", {"x": 1})

    fake_client.setex.assert_not_called()


@pytest.mark.asyncio
async def test_set_cached_json_does_nothing_when_client_is_none(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: None)

    # Must not raise and must silently return
    await set_cached_json("key", {"x": 1})


@pytest.mark.asyncio
async def test_set_cached_json_stores_serialized_data(monkeypatch) -> None:
    s = _patch_settings(monkeypatch)
    fake_client = AsyncMock()
    fake_client.setex = AsyncMock()
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    value = {"a": 1}
    await set_cached_json("my-suffix", value)

    fake_client.setex.assert_awaited_once_with(
        f"{CATALOG_CACHE_PREFIX}my-suffix",
        s.catalog_cache_ttl_seconds,
        json.dumps(value, default=str),
    )


@pytest.mark.asyncio
async def test_set_cached_json_silently_ignores_redis_exception(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    fake_client = AsyncMock()
    fake_client.setex = AsyncMock(side_effect=OSError("write failed"))
    monkeypatch.setattr(cc_module, "get_redis_client", lambda: fake_client)

    # Must not propagate the exception
    await set_cached_json("key", {"a": 1})


# ---------------------------------------------------------------------------
# Key builder helpers
# ---------------------------------------------------------------------------


def test_offerings_batch_cache_key_sorts_course_numbers() -> None:
    key1 = offerings_batch_cache_key(["B", "A"], academic_year=2024, semester_code=1)
    key2 = offerings_batch_cache_key(["A", "B"], academic_year=2024, semester_code=1)
    assert key1 == key2
    assert "A,B" in key1
    assert "y2024" in key1
    assert "s1" in key1


def test_offerings_batch_cache_key_none_values() -> None:
    key = offerings_batch_cache_key(["C1"], academic_year=None, semester_code=None)
    assert "yNone" in key
    assert "sNone" in key


def test_course_cache_key_format() -> None:
    assert course_cache_key("236781") == "course:236781"


def test_degree_programs_cache_key_format() -> None:
    assert degree_programs_cache_key() == "degree-programs:all"
