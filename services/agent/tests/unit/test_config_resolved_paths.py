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


def test_resolved_academic_wiki_path_prefers_docker_mount_when_configured_relative_path_is_dead(
    monkeypatch,
) -> None:
    """Reproduces the real bug: `.env`'s CATALOG_VAULT_WIKI_PATH is a path
    relative to the repo root (correct for local dev, where CWD is
    services/agent) that never resolves inside Docker (WORKDIR=/app) --
    even though the real wiki content is right there via the docker-compose
    volume mount at /app/data/academic/wiki. Without this fallback, every
    wiki retrieval silently missed real, existing pages."""
    settings = Settings(
        catalog_vault_wiki_path="../data-engineering/data/catalog_valut/catalog_valut/wiki",
        environment="development",
    )

    original_is_dir = Path.is_dir

    def fake_is_dir(self: Path) -> bool:
        if str(self) == "/app/data/academic/wiki":
            return True
        if str(self) == "../data-engineering/data/catalog_valut/catalog_valut/wiki":
            return False
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)

    assert settings.resolved_academic_wiki_path() == "/app/data/academic/wiki"
