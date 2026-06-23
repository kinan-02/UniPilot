from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev-only default for Docker first-run; rejected when ENVIRONMENT=production.
DEV_JWT_SECRET = "unipilot_dev_jwt_secret_change_in_production"
DEV_MONGO_PASSWORD = "unipilot_dev_password"

JWT_SECRET_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "replace_me_with_secure_jwt_secret",
        DEV_JWT_SECRET,
    }
)

MONGO_PASSWORD_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        DEV_MONGO_PASSWORD,
        "password",
        "changeme",
    }
)

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
)


class Settings(BaseSettings):
    service_name: str = "api"
    environment: str = "development"
    auto_seed_catalog: bool = False
    api_port: int = 8000
    mongo_uri: str | None = None
    mongo_root_password: str | None = None
    redis_url: str | None = None
    jwt_secret: str | None = None
    jwt_expires_in: str = "1h"
    bcrypt_salt_rounds: int = 12
    auth_rate_limit_window_ms: int = 60_000
    auth_rate_limit_max: int = 30
    ai_rate_limit_window_ms: int = 60_000
    ai_rate_limit_max: int = 10
    progress_rate_limit_window_ms: int = 60_000
    progress_rate_limit_max: int = 60
    cors_allowed_origins: str = ",".join(DEFAULT_CORS_ORIGINS)
    internal_service_token: str | None = None
    courses_collection: str = "courses"
    course_offerings_collection: str = "course_offerings"
    degree_programs_collection: str = "degree_programs"
    degree_requirements_collection: str = "degree_requirements"
    catalog_rules_collection: str = "catalog_rules"
    catalog_path_options_collection: str = "catalog_path_options"
    catalog_faculties_collection: str = "catalog_faculties"
    catalog_default_limit: int = 50
    catalog_max_limit: int = 200
    catalog_cache_enabled: bool = True
    catalog_cache_ttl_seconds: int = 300
    catalog_offerings_batch_max: int = 50
    completed_courses_collection: str = "completed_courses"
    semester_plans_collection: str = "semester_plans"
    academic_risks_collection: str = "academic_risks"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def require_jwt_secret(self) -> str:
        secret = (self.jwt_secret or "").strip()
        if not secret:
            raise RuntimeError(
                "JWT_SECRET is required. Copy .env.example to .env and set a strong secret."
            )
        if self.environment == "production":
            if secret in JWT_SECRET_PLACEHOLDERS:
                raise RuntimeError(
                    "JWT_SECRET must not use the development placeholder in production."
                )
            if len(secret) < 32:
                raise RuntimeError(
                    "JWT_SECRET must be at least 32 characters in production."
                )
        return secret

    def resolved_bcrypt_salt_rounds(self) -> int:
        rounds = int(self.bcrypt_salt_rounds)
        if rounds < 10:
            return 12
        return rounds

    def resolved_cors_origins(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in str(self.cors_allowed_origins).split(",")
            if origin.strip()
        ]
        return origins or list(DEFAULT_CORS_ORIGINS)

    @field_validator("mongo_root_password", mode="before")
    @classmethod
    def normalize_mongo_root_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    def validate_production_settings(self) -> None:
        self.require_jwt_secret()

        if self.environment != "production":
            return

        mongo_password = (self.mongo_root_password or "").strip()
        if not mongo_password or mongo_password in MONGO_PASSWORD_PLACEHOLDERS:
            raise RuntimeError(
                "MONGO_ROOT_PASSWORD must be a strong, unique value in production."
            )

        if self.auth_rate_limit_max > 10:
            raise RuntimeError(
                "AUTH_RATE_LIMIT_MAX must be <= 10 in production (recommended: 5)."
            )

        if self.ai_rate_limit_max > 10:
            raise RuntimeError(
                "AI_RATE_LIMIT_MAX must be <= 10 in production (recommended: 5)."
            )

        internal_token = (self.internal_service_token or "").strip()
        if not internal_token or len(internal_token) < 32:
            raise RuntimeError(
                "INTERNAL_SERVICE_TOKEN must be at least 32 characters in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
