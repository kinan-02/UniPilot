import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.config import get_settings
from app.db.mongo import close_mongo_client, set_test_database
from app.middleware.auth_rate_limiter import reset_in_memory_rate_limit_store
from app.security.refresh_tokens import reset_in_memory_refresh_token_store
from app.security.oauth_state import reset_in_memory_oauth_state_store
from app.main import create_app
from app.routes.auth import reset_user_indexes_state
from app.routes.completed_courses import reset_completed_course_indexes_state
from app.routes.academic_risks import reset_academic_risk_indexes_state
from app.routes.semester_plans import reset_semester_plan_indexes_state
from app.routes.student_profile import reset_student_profile_indexes_state


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()
    reset_user_indexes_state()
    reset_student_profile_indexes_state()
    reset_completed_course_indexes_state()
    reset_semester_plan_indexes_state()
    reset_academic_risk_indexes_state()
    reset_in_memory_rate_limit_store()
    reset_in_memory_refresh_token_store()
    reset_in_memory_oauth_state_store()
    reset_in_memory_oauth_state_store()
    yield
    get_settings.cache_clear()
    set_test_database(None)
    close_mongo_client()
    reset_user_indexes_state()
    reset_student_profile_indexes_state()
    reset_completed_course_indexes_state()
    reset_semester_plan_indexes_state()
    reset_academic_risk_indexes_state()
    reset_in_memory_rate_limit_store()
    reset_in_memory_refresh_token_store()
    reset_in_memory_oauth_state_store()


@pytest.fixture
async def mongo_database():
    client = AsyncMongoMockClient()
    database = client["unipilot_test"]
    yield database
    await client.drop_database("unipilot_test")
    client.close()


@pytest.fixture
async def auth_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "100")
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_MS", "60000")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    set_test_database(None)


@pytest.fixture
async def security_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "2")
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_MS", "60000")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    set_test_database(None)


@pytest.fixture
async def ai_security_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "100")
    monkeypatch.setenv("AI_RATE_LIMIT_MAX", "1")
    monkeypatch.setenv("AI_RATE_LIMIT_WINDOW_MS", "60000")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    set_test_database(None)


@pytest.fixture
async def progress_security_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "100")
    monkeypatch.setenv("PROGRESS_RATE_LIMIT_MAX", "1")
    monkeypatch.setenv("PROGRESS_RATE_LIMIT_WINDOW_MS", "60000")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    set_test_database(None)
