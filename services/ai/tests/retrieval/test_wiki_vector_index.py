"""Tests for wiki vector index helpers (no live embedding API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks, reset_wiki_index_cache
from app.retrieval.wiki_vector_index import (
    IndexedWikiChunk,
    WikiVectorIndex,
    backup_index_cache,
    canonical_wiki_root,
    chunk_cache_key,
    estimate_index_build_cost,
    estimate_query_embedding_cost,
    format_index_cache_loaded_message,
    load_index_from_cache,
    query_semantic_candidates,
    reset_wiki_vector_index_runtime_cache,
    restore_index_cache_from_backup,
    save_index_to_cache,
    verify_index_cache,
    _backup_latest_path,
    _compact_cache_path,
)


def setup_function() -> None:
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()


def test_chunk_cache_key_is_stable():
    chunk = WikiChunk(
        source_file="courses/009-dds/00940345.md",
        page_title="Discrete Math",
        section_title="Description",
        heading_path=("Discrete Math", "Description"),
        content="Students learn discrete mathematics.",
    )
    assert chunk_cache_key(chunk) == chunk_cache_key(chunk)


def test_estimate_index_build_cost_without_api(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "course.md").write_text(
        """---
title: Test Course
---
# Test Course
This is a sufficiently long course description for chunk indexing in tests.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACADEMIC_WIKI_PATH", str(wiki))
    get_settings.cache_clear()
    reset_wiki_index_cache()
    estimate = estimate_index_build_cost(wiki_root=str(wiki))
    assert estimate["chunkCount"] >= 1
    assert estimate["estimatedInputTokens"] > 0


def test_estimate_query_embedding_cost():
    estimate = estimate_query_embedding_cost(query_count=331)
    assert estimate["estimatedInputTokens"] == 331 * 12


def test_corrupt_compact_cache_is_removed(tmp_path):
    cache_file = tmp_path / "cache.json"
    compact = cache_file.with_name(f"{cache_file.stem}.compact.pkl.gz")
    compact.write_bytes(b"not-a-valid-gzip")
    loaded = load_index_from_cache(
        cache_file,
        wiki_root=str(tmp_path / "wiki"),
        model="test-model",
    )
    assert loaded is None
    assert not compact.is_file()


def _build_test_index(tmp_path: Path) -> tuple[Path, Path, WikiVectorIndex]:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "00940345.md").write_text(
        """---
title: Discrete Math
---
# Discrete Math
## Description
Students learn discrete mathematics for DDS.
""",
        encoding="utf-8",
    )
    chunks = list(load_wiki_chunks(str(wiki)))
    assert chunks
    chunk = chunks[0]
    index = WikiVectorIndex.from_entries(
        model="test-model",
        wiki_root=str(wiki.resolve()),
        entries=[
            IndexedWikiChunk(key=chunk_cache_key(chunk), chunk=chunk, vector=(1.0, 0.0))
        ],
    )
    cache_file = tmp_path / "cache.json"
    return wiki, cache_file, index


def test_cache_roundtrip(tmp_path):
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    loaded = load_index_from_cache(cache_file, wiki_root=str(wiki), model="test-model")
    assert loaded is not None
    assert len(loaded.entries) == 1


def test_cache_loads_with_relative_or_absolute_wiki_root(tmp_path):
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    loaded = load_index_from_cache(
        cache_file,
        wiki_root=str(wiki),
        model="test-model",
    )
    assert loaded is not None
    assert loaded.wiki_root == canonical_wiki_root(str(wiki))


def test_save_creates_backup_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_INDEX_CACHE_BACKUP_COUNT", "2")
    monkeypatch.setattr("app.retrieval.wiki_vector_index._MIN_BACKUP_BYTES", 1)
    get_settings.cache_clear()
    wiki, cache_file, index = _build_test_index(tmp_path)
    compact = _compact_cache_path(cache_file)
    compact.write_bytes(b"x" * 2048)
    save_index_to_cache(cache_file, index, allow_small=True)
    latest = _backup_latest_path(cache_file)
    meta = cache_file.with_name(f"{cache_file.stem}.meta.json")
    assert compact.is_file()
    assert latest.is_file()
    assert meta.is_file()


def test_restore_from_backup_when_primary_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.wiki_vector_index._MIN_BACKUP_BYTES", 1)
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    backup_index_cache(cache_path=cache_file)
    compact = _compact_cache_path(cache_file)
    compact.write_bytes(b"corrupt")
    loaded = load_index_from_cache(cache_file, wiki_root=str(wiki), model="test-model")
    assert loaded is not None
    assert compact.stat().st_size > 100


def test_verify_index_cache_reports_status(tmp_path):
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    report = verify_index_cache(cache_path=cache_file, wiki_root=str(wiki), model="test-model")
    assert report["ok"] is True
    assert report["entryCount"] == 1


def test_manual_backup_and_restore(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.wiki_vector_index._MIN_BACKUP_BYTES", 1)
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    compact = _compact_cache_path(cache_file)
    original_size = compact.stat().st_size
    backup_path = backup_index_cache(cache_path=cache_file)
    assert backup_path is not None
    compact.write_bytes(b"broken")
    restored = restore_index_cache_from_backup(cache_path=cache_file)
    assert restored is not None
    assert compact.stat().st_size == original_size
    loaded = load_index_from_cache(cache_file, wiki_root=str(wiki), model="test-model")
    assert loaded is not None


def test_format_index_cache_loaded_message(tmp_path):
    wiki, cache_file, index = _build_test_index(tmp_path)
    save_index_to_cache(cache_file, index, allow_small=True)
    message = format_index_cache_loaded_message(index, cache_file)
    assert "Loaded wiki index from disk (1 chunks," in message
    assert "KB" in message or "B" in message


@patch("app.retrieval.wiki_vector_index.get_wiki_vector_index")
@patch("app.retrieval.wiki_vector_index.embed_query_cached")
def test_query_semantic_candidates_uses_index(mock_embed_query_cached, mock_get_index):
    chunk = WikiChunk(
        source_file="courses/009-dds/00940345.md",
        page_title="Discrete Math",
        section_title="Description",
        heading_path=("Discrete Math", "Description"),
        content="Students learn discrete mathematics for DDS.",
    )
    from app.retrieval.wiki_vector_index import IndexedWikiChunk

    mock_get_index.return_value = WikiVectorIndex.from_entries(
        model="test-model",
        wiki_root="/wiki",
        entries=[IndexedWikiChunk(key=chunk_cache_key(chunk), chunk=chunk, vector=(1.0, 0.0))],
    )
    mock_embed_query_cached.return_value = (1.0, 0.0)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    results = query_semantic_candidates(query="discrete math", wiki_root="/wiki", limit=3)
    monkeypatch.undo()
    assert results
    assert results[0][0].page_title == "Discrete Math"
