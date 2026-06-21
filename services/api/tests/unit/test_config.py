import pytest

from app.config import DEV_JWT_SECRET, JWT_SECRET_PLACEHOLDERS, Settings


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
