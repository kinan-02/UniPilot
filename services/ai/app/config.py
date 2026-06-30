"""AI service configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "ai"
    environment: str = "development"
    ai_service_port: int = 3001
    internal_service_token: str | None = None

    academic_wiki_path: str = "/app/data/academic/wiki"
    academic_technion_raw_dir: str = "/app/data/raw/technion"
    academic_default_semester_file: str = "courses_2025_201.json"
    academic_catalog_json: str = "/app/data/raw/technion/courses_2025_201.json"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_chat_model: str = "gpt-5-mini"
    advisor_max_retrieval_iterations: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
