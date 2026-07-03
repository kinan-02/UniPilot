"""MAS settings resolution tests."""

from app.config import Settings


def test_llm_settings_fall_back_to_shared_openai_env(monkeypatch) -> None:
    monkeypatch.setenv("MAS_OPENAI_API_KEY", "")
    monkeypatch.setenv("MAS_OPENAI_BASE_URL", "")
    monkeypatch.setenv("MAS_OPENAI_CHAT_MODEL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "deepseek-v4-pro")

    settings = Settings()

    assert settings.resolved_mas_openai_api_key() == "shared-key"
    assert settings.resolved_mas_openai_base_url() == "https://api.deepseek.com"
    assert settings.resolved_mas_openai_chat_model() == "deepseek-v4-pro"
    assert settings.llm_configured() is True


def test_resolved_technion_raw_dir_falls_back_to_catalog_parent(monkeypatch, tmp_path) -> None:
    catalog = tmp_path / "courses.json"
    catalog.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("ACADEMIC_TECHNION_RAW_DIR", "")
    monkeypatch.setenv("ACADEMIC_CATALOG_JSON", str(catalog))

    settings = Settings()
    assert settings.resolved_technion_raw_dir() == str(tmp_path)


def test_resolved_default_semester_file_from_catalog_name(monkeypatch, tmp_path) -> None:
    catalog = tmp_path / "courses_2025_201.json"
    catalog.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("ACADEMIC_DEFAULT_SEMESTER_FILE", "")
    monkeypatch.setenv("ACADEMIC_CATALOG_JSON", str(catalog))

    settings = Settings()
    assert settings.resolved_default_semester_file() == "courses_2025_201.json"


def test_mas_specific_llm_settings_override_shared_openai(monkeypatch) -> None:
    monkeypatch.setenv("MAS_OPENAI_API_KEY", "mas-key")
    monkeypatch.setenv("MAS_OPENAI_BASE_URL", "https://mas.example")
    monkeypatch.setenv("MAS_OPENAI_CHAT_MODEL", "mas-model")
    monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "deepseek-v4-pro")

    settings = Settings()

    assert settings.resolved_mas_openai_api_key() == "mas-key"
    assert settings.resolved_mas_openai_base_url() == "https://mas.example"
    assert settings.resolved_mas_openai_chat_model() == "mas-model"
