from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "data-engineering"
    environment: str = "development"
    mongo_uri: str = "mongodb://localhost:27017/unipilot_python"
    mongo_db_name: str = "unipilot_python"
    log_level: str = "INFO"
    staging_courses_collection: str = "staging_courses"
    staging_course_offerings_collection: str = "staging_course_offerings"
    staging_degree_requirements_collection: str = "staging_degree_requirements"
    staging_degree_programs_collection: str = "staging_degree_programs"
    staging_catalog_rules_collection: str = "staging_catalog_rules"
    staging_data_quality_reports_collection: str = "staging_data_quality_reports"
    staging_ingestion_runs_collection: str = "staging_ingestion_runs"
    dds_catalog_pdf_path: str | None = None
    dds_catalog_md_path: str | None = None
    dds_catalog_output_dir: str = "data/generated/technion/dds_catalog"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
