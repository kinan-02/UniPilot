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


def test_resolved_google_oauth_redirect_uri_uses_explicit_value() -> None:
    settings = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        google_oauth_redirect_uri="https://example.com/custom/callback",
    )
    assert settings.resolved_google_oauth_redirect_uri() == "https://example.com/custom/callback"


def test_google_oauth_enabled_requires_client_credentials() -> None:
    settings = Settings(environment="development", jwt_secret=DEV_JWT_SECRET)
    assert settings.google_oauth_enabled() is False
    settings_with_google = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        google_oauth_client_id="client",
        google_oauth_client_secret="secret",
    )
    assert settings_with_google.google_oauth_enabled() is True


def test_e2e_google_oauth_stub_disabled_in_production() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        google_oauth_client_id="client",
        google_oauth_client_secret="secret",
        e2e_google_oauth_stub=True,
    )
    assert settings.e2e_google_oauth_stub_enabled() is False


def test_e2e_google_oauth_stub_requires_flag_and_credentials() -> None:
    settings = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        google_oauth_client_id="client",
        google_oauth_client_secret="secret",
        e2e_google_oauth_stub=False,
    )
    assert settings.e2e_google_oauth_stub_enabled() is False

    enabled = settings.model_copy(update={"e2e_google_oauth_stub": True})
    assert enabled.e2e_google_oauth_stub_enabled() is True


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


def test_resolved_ai_service_url_uses_default_when_unset() -> None:
    settings = Settings(ai_service_url=None)
    assert settings.resolved_ai_service_url() == "http://ai:3001"


def test_resolved_transcript_parser_url_uses_default_when_unset() -> None:
    settings = Settings(transcript_parser_url=None)
    assert settings.resolved_transcript_parser_url() == "http://transcript-parser:8010"


def test_resolved_transcript_parser_url_strips_trailing_slash() -> None:
    settings = Settings(transcript_parser_url="http://parser:9000/")
    assert settings.resolved_transcript_parser_url() == "http://parser:9000"


def test_resolved_internal_service_token_strips_whitespace() -> None:
    settings = Settings(internal_service_token="  secret-token  ")
    assert settings.resolved_internal_service_token() == "secret-token"


def test_validate_production_settings_rejects_high_transcript_import_rate_limit() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 32,
        mongo_root_password="strong-production-mongo-password",
        internal_service_token="y" * 32,
        auth_rate_limit_max=5,
        ai_rate_limit_max=5,
        transcript_import_rate_limit_max=30,
    )
    with pytest.raises(RuntimeError, match="TRANSCRIPT_IMPORT_RATE_LIMIT_MAX"):
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


def test_microsoft_oauth_enabled_requires_client_and_encryption_key() -> None:
    settings = Settings(environment="development", jwt_secret=DEV_JWT_SECRET)
    assert settings.microsoft_oauth_enabled() is False

    configured = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        microsoft_client_id="client-id",
        microsoft_token_encryption_key="encryption-key",
    )
    assert configured.microsoft_oauth_enabled() is True


def test_resolved_microsoft_redirect_uri_defaults_to_web_app_callback() -> None:
    settings = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        web_app_url="http://localhost:3000",
    )
    assert (
        settings.resolved_microsoft_redirect_uri()
        == "http://localhost:3000/api/integrations/outlook/callback"
    )


def test_resolved_microsoft_redirect_uri_uses_explicit_value() -> None:
    settings = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        microsoft_redirect_uri="https://example.com/outlook/callback",
    )
    assert settings.resolved_microsoft_redirect_uri() == "https://example.com/outlook/callback"


def test_require_microsoft_token_encryption_key() -> None:
    settings = Settings(environment="development", jwt_secret=DEV_JWT_SECRET)
    with pytest.raises(RuntimeError, match="MICROSOFT_TOKEN_ENCRYPTION_KEY"):
        settings.require_microsoft_token_encryption_key()

    configured = Settings(
        environment="development",
        jwt_secret=DEV_JWT_SECRET,
        microsoft_token_encryption_key="key-material",
    )
    assert configured.require_microsoft_token_encryption_key() == b"key-material"

