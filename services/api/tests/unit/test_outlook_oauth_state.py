import pytest

from app.security.outlook_oauth_state import (
    InMemoryOutlookOAuthStateStore,
    consume_outlook_oauth_state,
    issue_outlook_oauth_state,
    reset_in_memory_outlook_oauth_state_store,
    resolve_outlook_oauth_state_store,
    set_outlook_oauth_state_store,
)


@pytest.mark.asyncio
async def test_outlook_oauth_state_store_roundtrip():
    reset_in_memory_outlook_oauth_state_store()
    state = await issue_outlook_oauth_state(
        user_id="507f1f77bcf86cd799439011",
        code_verifier="verifier-123",
    )
    consumed = await consume_outlook_oauth_state(state)
    assert consumed == ("507f1f77bcf86cd799439011", "verifier-123")
    assert await consume_outlook_oauth_state(state) is None


@pytest.mark.asyncio
async def test_in_memory_store_purge_and_invalid_consume():
    store = InMemoryOutlookOAuthStateStore()
    await store.store("state", user_id="u1", code_verifier="v1")
    assert await store.consume("missing") is None
    store._entries[next(iter(store._entries))] = ("u1", "v1", 0)
    store._purge_expired()
    assert not store._entries
    store.reset()


def test_resolve_outlook_oauth_state_store_uses_redis_when_configured(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    from app.config import get_settings

    get_settings.cache_clear()
    set_outlook_oauth_state_store(None)
    store = resolve_outlook_oauth_state_store()
    assert store.__class__.__name__ == "RedisOutlookOAuthStateStore"
    set_outlook_oauth_state_store(None)
    get_settings.cache_clear()
