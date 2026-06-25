"""Filesystem paths for the data-engineering service."""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def service_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_under_service_root(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (service_root() / path).resolve()


def catalog_vault_root() -> Path:
    configured = get_settings().catalog_vault_path
    return _resolve_under_service_root(Path(configured))


def _wiki_root_candidates(vault_root: Path) -> list[Path]:
    candidates = [
        vault_root / "wiki",
        vault_root / "catalog_valut" / "wiki",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _score_wiki_root(candidate: Path) -> int:
    if not candidate.is_dir():
        return -1

    score = 0
    if (candidate / "entities" / "tracks").is_dir():
        score += 10_000
    if (candidate / "entities" / "faculties").is_dir():
        score += 5_000
    if (candidate / "courses").is_dir():
        score += sum(1 for _ in (candidate / "courses").rglob("*.md"))
    score += sum(1 for _ in candidate.rglob("*.md"))
    return score


def resolve_catalog_vault_wiki_root(vault_root: Path | None = None) -> Path:
    """Pick the richest wiki tree under the configured vault root."""
    root = vault_root or catalog_vault_root()
    candidates = _wiki_root_candidates(root)
    best = max(candidates, key=_score_wiki_root)
    if _score_wiki_root(best) < 0:
        raise FileNotFoundError(
            f"No catalog wiki found under {root}. "
            "Expected wiki/ or catalog_valut/wiki/ with markdown pages."
        )
    return best.resolve()


def catalog_vault_wiki_root() -> Path:
    return resolve_catalog_vault_wiki_root()


def default_catalog_export_dir() -> Path:
    return _resolve_under_service_root(Path(get_settings().dds_catalog_output_dir))


def default_catalog_reviewed_path() -> Path:
    return default_catalog_export_dir() / "catalog_reviewed.json"


def default_readiness_path() -> Path:
    return default_catalog_export_dir() / "catalog_phase8_readiness_check.json"
