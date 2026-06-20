import time

import pytest

from app.config import get_settings
from app.security.jwt import create_access_token, verify_access_token


@pytest.fixture(autouse=True)
def jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_access_token_signs_user_claims():
    token = create_access_token(
        user_id="507f1f77bcf86cd799439011",
        email="user@example.com",
    )
    payload = verify_access_token(token)

    assert payload["sub"] == "507f1f77bcf86cd799439011"
    assert payload["email"] == "user@example.com"


def test_verify_access_token_raises_for_malformed_token():
    with pytest.raises(Exception):
        verify_access_token("malformed-token")


def test_verify_access_token_raises_for_expired_token(monkeypatch):
    monkeypatch.setenv("JWT_EXPIRES_IN", "1ms")
    get_settings.cache_clear()

    token = create_access_token(
        user_id="507f1f77bcf86cd799439011",
        email="user@example.com",
    )

    time.sleep(0.01)

    with pytest.raises(Exception):
        verify_access_token(token)
