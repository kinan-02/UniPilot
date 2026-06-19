import pytest
import mongomock

from app.config import get_settings
from app.db import close_mongo_client, set_test_database


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_de_test")
    monkeypatch.setenv("MONGO_DB_NAME", "unipilot_de_test")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()
    yield
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()


@pytest.fixture
def mongo_database():
    client = mongomock.MongoClient()
    database = client["unipilot_de_test"]
    set_test_database(database)
    yield database
    set_test_database(None)
