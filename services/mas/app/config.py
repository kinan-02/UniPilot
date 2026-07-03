"""MAS service configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "mas"
    environment: str = "development"
    mas_service_port: int = 3003
    internal_service_token: str | None = None

    mongo_uri: str | None = None
    redis_url: str | None = None
    mas_queue_name: str = "mas_agent_jobs"

    academic_wiki_path: str = "/app/data/academic/wiki"
    academic_technion_raw_dir: str = "/app/data/raw/technion"
    academic_default_semester_file: str = "courses_2025_201.json"
    academic_catalog_json: str = "/app/data/raw/technion/courses_2025_201.json"

    mas_openai_api_key: str | None = Field(default=None, validation_alias="MAS_OPENAI_API_KEY")
    mas_openai_base_url: str | None = Field(default=None, validation_alias="MAS_OPENAI_BASE_URL")
    mas_openai_chat_model: str | None = Field(
        default=None,
        validation_alias="MAS_OPENAI_CHAT_MODEL",
    )
    # Shared fallbacks when MAS_* vars are unset (same .env as the ai advisor).
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_chat_model: str | None = Field(default=None, validation_alias="OPENAI_CHAT_MODEL")
    mas_max_negotiation_rounds: int = Field(default=3, validation_alias="MAS_MAX_NEGOTIATION_ROUNDS")
    mas_planner_max_tool_iterations: int = Field(
        default=5,
        validation_alias="MAS_PLANNER_MAX_TOOL_ITERATIONS",
    )
    mas_worker_enabled: bool = Field(default=True, validation_alias="MAS_WORKER_ENABLED")

    api_service_url: str | None = Field(default=None, validation_alias="API_SERVICE_URL")
    api_request_timeout_seconds: int = Field(default=30, validation_alias="API_REQUEST_TIMEOUT_SECONDS")

    agent_sessions_collection: str = "agent_sessions"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def resolved_technion_raw_dir(self) -> str:
        raw = (self.academic_technion_raw_dir or "").strip()
        if raw:
            return raw
        catalog = Path(self.academic_catalog_json)
        if catalog.is_file():
            return str(catalog.parent)
        return raw

    def resolved_default_semester_file(self) -> str | None:
        explicit = (self.academic_default_semester_file or "").strip()
        if explicit:
            return explicit
        catalog = Path(self.academic_catalog_json)
        if catalog.is_file():
            return catalog.name
        return None

    def is_graph_configured(self) -> bool:
        wiki = (self.academic_wiki_path or "").strip()
        raw = self.resolved_technion_raw_dir()
        return bool(wiki and raw)

    def resolved_mas_openai_api_key(self) -> str:
        return (self.mas_openai_api_key or self.openai_api_key or "").strip()

    def resolved_mas_openai_base_url(self) -> str | None:
        raw = (self.mas_openai_base_url or self.openai_base_url or "").strip()
        return raw or None

    def resolved_mas_openai_chat_model(self) -> str:
        explicit = (self.mas_openai_chat_model or "").strip()
        if explicit:
            return explicit
        shared = (self.openai_chat_model or "").strip()
        if shared:
            return shared
        return "gpt-5-mini"

    def llm_configured(self) -> bool:
        return bool(self.resolved_mas_openai_api_key())

    def resolved_api_service_url(self) -> str | None:
        raw = (self.api_service_url or "").strip().rstrip("/")
        return raw or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
