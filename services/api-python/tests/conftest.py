import pytest

from app.config import get_settings
from app.db.mongo import close_mongo_client


@pytest.fixture(autouse=True)
def reset_runtime_state():
    get_settings.cache_clear()
    close_mongo_client()
    yield
    get_settings.cache_clear()
    close_mongo_client()
