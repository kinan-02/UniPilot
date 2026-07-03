import pytest
from mongomock_motor import AsyncMongoMockClient

from app.config import get_settings
from app.db.mongo import close_mongo_client, set_test_database


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-service-token")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test-client-id")
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


@pytest.fixture
def internal_token() -> str:
    return "test-internal-service-token"


@pytest.fixture
def sample_user_id() -> str:
    return "507f1f77bcf86cd799439011"
