import time

import pytest

from app.config import get_settings
from app.security.jwt import create_access_token, parse_expires_in, verify_access_token


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


class TestParseExpiresIn:
    def test_parse_hours(self):
        from datetime import timedelta
        delta = parse_expires_in("1h")
        assert delta == timedelta(hours=1)

    def test_parse_minutes(self):
        from datetime import timedelta
        delta = parse_expires_in("30m")
        assert delta == timedelta(minutes=30)

    def test_parse_seconds(self):
        from datetime import timedelta
        delta = parse_expires_in("3600s")
        assert delta == timedelta(seconds=3600)

    def test_parse_milliseconds(self):
        from datetime import timedelta
        delta = parse_expires_in("500ms")
        assert delta == timedelta(milliseconds=500)

    def test_parse_days(self):
        from datetime import timedelta
        delta = parse_expires_in("7d")
        assert delta == timedelta(days=7)

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported JWT expires format"):
            parse_expires_in("1year")

    def test_invalid_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported JWT expires format"):
            parse_expires_in("invalid")

    def test_whitespace_stripped_before_parsing(self):
        from datetime import timedelta
        delta = parse_expires_in("  2h  ")
        assert delta == timedelta(hours=2)


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
