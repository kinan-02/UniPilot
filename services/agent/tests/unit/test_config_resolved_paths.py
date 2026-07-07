"""Unit tests for Docker-path-vs-local-dev fallback in resolved data paths."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, _resolve_repo_root


def _local_technion_dir() -> Path:
    return _resolve_repo_root() / "services" / "data-engineering" / "data" / "raw" / "technion"


def test_resolved_technion_raw_dir_prefers_local_dev_dir_over_docker_path() -> None:
    settings = Settings(technion_raw_dir="/app/data/raw/technion", environment="development")
    assert settings.resolved_technion_raw_dir() == str(_local_technion_dir())


def test_resolved_technion_raw_dir_keeps_docker_path_in_production() -> None:
    settings = Settings(technion_raw_dir="/app/data/raw/technion", environment="production")
    assert settings.resolved_technion_raw_dir() == "/app/data/raw/technion"


def test_resolved_technion_raw_dir_keeps_explicit_non_docker_path() -> None:
    settings = Settings(technion_raw_dir="/some/explicit/local/path", environment="development")
    assert settings.resolved_technion_raw_dir() == "/some/explicit/local/path"


def test_resolved_academic_wiki_path_prefers_local_dev_dir_over_docker_path() -> None:
    settings = Settings(catalog_vault_wiki_path="/app/data/academic/wiki", environment="development")
    local = Path(__file__).resolve().parents[2] / "data" / "academic" / "wiki"
    if local.is_dir():
        assert settings.resolved_academic_wiki_path() == str(local)
    else:
        assert settings.resolved_academic_wiki_path() == "/app/data/academic/wiki"


def test_resolved_academic_wiki_path_keeps_docker_path_in_production() -> None:
    settings = Settings(catalog_vault_wiki_path="/app/data/academic/wiki", environment="production")
    assert settings.resolved_academic_wiki_path() == "/app/data/academic/wiki"


def test_resolved_academic_wiki_path_keeps_explicit_non_docker_path() -> None:
    settings = Settings(catalog_vault_wiki_path="/some/explicit/local/path", environment="development")
    assert settings.resolved_academic_wiki_path() == "/some/explicit/local/path"
