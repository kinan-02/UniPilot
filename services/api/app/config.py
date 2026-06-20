from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "api"
    environment: str = "development"
    api_port: int = 8000
    mongo_uri: str | None = None
    redis_url: str | None = None
    jwt_secret: str | None = None
    jwt_expires_in: str = "1h"
    bcrypt_salt_rounds: int = 12
    auth_rate_limit_window_ms: int = 60_000
    auth_rate_limit_max: int = 5
    courses_collection: str = "courses"
    course_offerings_collection: str = "course_offerings"
    degree_programs_collection: str = "degree_programs"
    degree_requirements_collection: str = "degree_requirements"
    catalog_rules_collection: str = "catalog_rules"
    catalog_default_limit: int = 50
    catalog_max_limit: int = 200
    completed_courses_collection: str = "completed_courses"
    semester_plans_collection: str = "semester_plans"
    academic_risks_collection: str = "academic_risks"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def require_jwt_secret(self) -> str:
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET is required")
        return self.jwt_secret

    def resolved_bcrypt_salt_rounds(self) -> int:
        rounds = int(self.bcrypt_salt_rounds)
        if rounds < 10:
            return 12
        return rounds


@lru_cache
def get_settings() -> Settings:
    return Settings()
