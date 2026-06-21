import pytest

from app.config import DEV_JWT_SECRET, JWT_SECRET_PLACEHOLDERS, Settings, get_settings


def test_require_jwt_secret_accepts_dev_default_in_development() -> None:
    settings = Settings(environment="development", jwt_secret=DEV_JWT_SECRET)
    assert settings.require_jwt_secret() == DEV_JWT_SECRET


def test_require_jwt_secret_rejects_placeholder_in_production() -> None:
    settings = Settings(environment="production", jwt_secret=DEV_JWT_SECRET)
    with pytest.raises(RuntimeError, match="development placeholder"):
        settings.require_jwt_secret()


def test_require_jwt_secret_rejects_short_secret_in_production() -> None:
    settings = Settings(environment="production", jwt_secret="too-short-for-production-use")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        settings.require_jwt_secret()


def test_require_jwt_secret_accepts_strong_production_secret() -> None:
    secret = "x" * 32
    settings = Settings(environment="production", jwt_secret=secret)
    assert settings.require_jwt_secret() == secret


def test_legacy_placeholder_is_rejected_in_production() -> None:
    assert "replace_me_with_secure_jwt_secret" in JWT_SECRET_PLACEHOLDERS


# ---------------------------------------------------------------------------
# require_jwt_secret — empty / None secret (line 53)
# ---------------------------------------------------------------------------


def test_require_jwt_secret_raises_when_secret_is_none() -> None:
    settings = Settings(environment="development", jwt_secret=None)
    with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
        settings.require_jwt_secret()


def test_require_jwt_secret_raises_when_secret_is_empty_string() -> None:
    settings = Settings(environment="development", jwt_secret="   ")  # whitespace-only
    with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
        settings.require_jwt_secret()


# ---------------------------------------------------------------------------
# resolved_bcrypt_salt_rounds — below minimum (line 70)
# ---------------------------------------------------------------------------


def test_resolved_bcrypt_salt_rounds_returns_12_when_below_minimum() -> None:
    settings = Settings(environment="development", jwt_secret="s", bcrypt_salt_rounds=8)
    assert settings.resolved_bcrypt_salt_rounds() == 12


def test_resolved_bcrypt_salt_rounds_returns_value_at_minimum() -> None:
    settings = Settings(environment="development", jwt_secret="s", bcrypt_salt_rounds=10)
    assert settings.resolved_bcrypt_salt_rounds() == 10


def test_resolved_bcrypt_salt_rounds_returns_value_above_minimum() -> None:
    settings = Settings(environment="development", jwt_secret="s", bcrypt_salt_rounds=14)
    assert settings.resolved_bcrypt_salt_rounds() == 14


# ---------------------------------------------------------------------------
# get_settings — lru_cache factory (line 76)
# ---------------------------------------------------------------------------


def test_get_settings_returns_settings_instance(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-factory")
    get_settings.cache_clear()
    result = get_settings()
    assert isinstance(result, Settings)
    get_settings.cache_clear()


def test_get_settings_returns_same_cached_instance(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-factory")
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
