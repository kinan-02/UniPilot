from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "data-engineering"
    environment: str = "development"
    mongo_uri: str = "mongodb://localhost:27017/unipilot_python"
    mongo_db_name: str = "unipilot_python"
    log_level: str = "INFO"
    staging_courses_collection: str = "staging_courses"
    staging_degree_requirements_collection: str = "staging_degree_requirements"
    staging_ingestion_runs_collection: str = "staging_ingestion_runs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
