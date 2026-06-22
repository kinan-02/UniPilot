import pytest

from app.config import DEV_JWT_SECRET, DEV_MONGO_PASSWORD, JWT_SECRET_PLACEHOLDERS, Settings, get_settings


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


def test_resolved_cors_origins_splits_env_value() -> None:
    settings = Settings(
        environment="development",
        jwt_secret="s",
        cors_allowed_origins="https://app.example.com, https://admin.example.com",
    )
    assert settings.resolved_cors_origins() == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_validate_production_settings_rejects_weak_mongo_password() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        mongo_root_password=DEV_MONGO_PASSWORD,
        internal_service_token="y" * 32,
        auth_rate_limit_max=5,
        ai_rate_limit_max=5,
    )
    with pytest.raises(RuntimeError, match="MONGO_ROOT_PASSWORD"):
        settings.validate_production_settings()


def test_validate_production_settings_rejects_high_auth_rate_limit() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        mongo_root_password="strong-production-mongo-password",
        internal_service_token="y" * 32,
        auth_rate_limit_max=30,
        ai_rate_limit_max=5,
    )
    with pytest.raises(RuntimeError, match="AUTH_RATE_LIMIT_MAX"):
        settings.validate_production_settings()


def test_validate_production_settings_rejects_high_ai_rate_limit() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        mongo_root_password="strong-production-mongo-password",
        internal_service_token="y" * 32,
        auth_rate_limit_max=5,
        ai_rate_limit_max=30,
    )
    with pytest.raises(RuntimeError, match="AI_RATE_LIMIT_MAX"):
        settings.validate_production_settings()


def test_validate_production_settings_requires_internal_service_token() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        mongo_root_password="strong-production-mongo-password",
        internal_service_token="short",
        auth_rate_limit_max=5,
        ai_rate_limit_max=5,
    )
    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_TOKEN"):
        settings.validate_production_settings()
