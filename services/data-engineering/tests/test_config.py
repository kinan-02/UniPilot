from app.config import get_settings


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://mongo:27017/custom_db?authSource=admin")
    monkeypatch.setenv("MONGO_DB_NAME", "custom_db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.mongo_uri.endswith("custom_db?authSource=admin")
    assert settings.mongo_db_name == "custom_db"
    assert settings.log_level == "DEBUG"
    assert settings.environment == "test"
    assert settings.staging_courses_collection == "staging_courses"


def test_staging_collection_names_are_configured():
    settings = get_settings()

    assert settings.staging_degree_requirements_collection == "staging_degree_requirements"
    assert settings.staging_ingestion_runs_collection == "staging_ingestion_runs"
