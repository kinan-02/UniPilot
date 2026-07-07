"""In-process wiki/catalog lookup cache for eval runs (Phase 28.1).

Read-only, per-process caches — safe for deterministic eval use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.retrieval.wiki_paths import resolve_wiki_root
from app.services.wiki_lookup_parser import (
    build_track_code_index,
    find_course_wiki_page,
    find_regulations_page,
    find_track_wiki_page,
    parse_course_page,
    parse_track_page,
    read_wiki_page,
    relative_wiki_path,
)

_wiki_text_cache: dict[str, str] = {}
_course_record_cache: dict[tuple[str, str], dict[str, Any]] = {}
_track_record_cache: dict[tuple[str, str], dict[str, Any]] = {}
_course_path_index: dict[str, dict[str, str]] = {}
_track_code_index_cache: dict[str, dict[str, str]] = {}
_regulation_text_cache: dict[str, str] = {}
_cache_stats: dict[str, int] = {"wikiReads": 0, "wikiReadHits": 0, "courseLookups": 0, "courseLookupHits": 0}


def cache_stats() -> dict[str, int]:
    return dict(_cache_stats)


def reset_wiki_eval_cache() -> None:
    _wiki_text_cache.clear()
    _course_record_cache.clear()
    _track_record_cache.clear()
    _course_path_index.clear()
    _track_code_index_cache.clear()
    _regulation_text_cache.clear()
    for key in _cache_stats:
        _cache_stats[key] = 0


def _wiki_root(settings: Settings | None = None) -> Path | None:
    cfg = settings or get_settings()
    configured = (cfg.resolved_academic_wiki_path() or "").strip()
    if not configured:
        return None
    return Path(resolve_wiki_root(configured))


def cached_read_wiki_page(path: Path) -> str | None:
    key = str(path.resolve())
    _cache_stats["wikiReads"] += 1
    if key in _wiki_text_cache:
        _cache_stats["wikiReadHits"] += 1
        return _wiki_text_cache[key]
    text = read_wiki_page(path)
    if text is not None:
        _wiki_text_cache[key] = text
    return text


def _build_course_path_index(wiki_root: Path) -> dict[str, str]:
    root_key = str(wiki_root.resolve())
    if root_key in _course_path_index:
        return _course_path_index[root_key]

    index: dict[str, str] = {}
    courses_dir = wiki_root / "courses"
    if courses_dir.is_dir():
        for path in courses_dir.rglob("*.md"):
            stem = path.stem.split("-", 1)[0]
            digits = "".join(ch for ch in stem if ch.isdigit())
            if len(digits) >= 5:
                index.setdefault(digits, str(path))
    _course_path_index[root_key] = index
    return index


def cached_find_course_wiki_page(wiki_root: Path, course_number: str) -> Path | None:
    root_key = str(wiki_root.resolve())
    index = _build_course_path_index(wiki_root)
    normalized = "".join(ch for ch in course_number if ch.isdigit())
    if normalized in index:
        return Path(index[normalized])
    return find_course_wiki_page(wiki_root, course_number)


def cached_course_by_code(wiki_root: Path, course_number: str) -> dict[str, Any] | None:
    cache_key = (str(wiki_root.resolve()), course_number)
    _cache_stats["courseLookups"] += 1
    if cache_key in _course_record_cache:
        _cache_stats["courseLookupHits"] += 1
        return dict(_course_record_cache[cache_key])

    path = cached_find_course_wiki_page(wiki_root, course_number)
    if path is None:
        return None
    text = cached_read_wiki_page(path)
    if not text:
        return None
    record = parse_course_page(text, source_path=relative_wiki_path(path, wiki_root))
    _course_record_cache[cache_key] = dict(record)
    return record


def cached_track_by_slug(wiki_root: Path, track_slug: str) -> dict[str, Any] | None:
    cache_key = (str(wiki_root.resolve()), track_slug.strip().lower())
    if cache_key in _track_record_cache:
        return dict(_track_record_cache[cache_key])
    path = find_track_wiki_page(wiki_root, track_slug)
    if path is None:
        return None
    text = cached_read_wiki_page(path)
    if not text:
        return None
    record = parse_track_page(text, source_path=relative_wiki_path(path, wiki_root))
    _track_record_cache[cache_key] = dict(record)
    return record


def cached_track_code_index(wiki_root: Path) -> dict[str, str]:
    root_key = str(wiki_root.resolve())
    if root_key not in _track_code_index_cache:
        _track_code_index_cache[root_key] = build_track_code_index(wiki_root)
    return _track_code_index_cache[root_key]


def cached_regulation_text(wiki_root: Path) -> str | None:
    root_key = str(wiki_root.resolve())
    if root_key in _regulation_text_cache:
        return _regulation_text_cache[root_key]
    path = find_regulations_page(wiki_root)
    if path is None:
        return None
    text = cached_read_wiki_page(path)
    if text is not None:
        _regulation_text_cache[root_key] = text
    return text


def warm_wiki_eval_cache(*, settings: Settings | None = None) -> str:
    """Pre-index wiki paths and warm shared lookups once per eval process."""
    wiki_root = _wiki_root(settings)
    if wiki_root is None:
        return ""
    _build_course_path_index(wiki_root)
    cached_track_code_index(wiki_root)
    cached_regulation_text(wiki_root)
    return str(wiki_root)
