import pytest
from mongomock_motor import AsyncMongoMockClient

from app.config import get_settings
from app.db.mongo import close_mongo_client, set_test_database


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    # Setting to an empty string (not `delenv`) is deliberate: pydantic-settings
    # falls back to reading `.env` for any field absent from os.environ, so a
    # developer's real local `.env` (with a live OPENAI_API_KEY) would leak
    # into tests otherwise. An explicit empty value in os.environ wins.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AGENT_LLM_EXPLANATION_ENABLED", "false")
    monkeypatch.setenv("AGENT_LLM_INTENT_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED", "false")
    monkeypatch.setenv("AGENT_LLM_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("AGENT_TASK_UNDERSTANDING_ENABLED", "false")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-service-token")
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()
    yield
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()


@pytest.fixture
async def mongo_database():
    client = AsyncMongoMockClient()
    database = client["unipilot_test"]
    yield database
    await client.drop_database("unipilot_test")
    client.close()
