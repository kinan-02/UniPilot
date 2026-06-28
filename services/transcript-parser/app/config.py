"""Transcript parser service configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "transcript-parser"
    environment: str = "development"
    transcript_parser_port: int = 8010
    internal_service_token: str | None = None
    max_upload_bytes: int = 5 * 1024 * 1024
    parse_timeout_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
