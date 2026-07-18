"""Tests for the Pinecone-backed wiki vector index (never touches the network)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks, reset_wiki_index_cache
from app.retrieval.vector_store import VectorStoreError
from app.retrieval.wiki_vector_index import (
    chunk_metadata,
    chunk_vector_id,
    estimate_index_build_cost,
    estimate_query_embedding_cost,
    fetch_chunk_vectors,
    query_semantic_candidates,
    reset_wiki_vector_index_runtime_cache,
)

# A Hebrew section heading, as ~every real page in this corpus has. This is
# what makes the id scheme load-bearing rather than cosmetic.
_HEBREW_SECTION = "פרטי הקורס בעברית"

_WIKI_PAGE = f"""---
title: Discrete Math
---
# Discrete Math
## Description
Students learn discrete mathematics for DDS in this section of the page.
## {_HEBREW_SECTION}
תיאור הקורס בעברית עם מספיק תוכן כדי להיחשב מקטע לאינדוקס.
"""


class _FakeVectorStore:
    """In-memory stand-in implementing the `VectorStore` protocol."""

    def __init__(
        self,
        vectors: dict[str, tuple[float, ...]] | None = None,
        *,
        matches: list[tuple[str, float]] | None = None,
        fail: bool = False,
    ) -> None:
        self.vectors = dict(vectors or {})
        self._matches = matches
        self.fail = fail
        self.query_calls: list[tuple[tuple[float, ...], int]] = []
        self.fetch_calls: list[list[str]] = []

    def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[str, float]]:
        if self.fail:
            raise VectorStoreError("pinecone_query_failed: simulated")
        self.query_calls.append((tuple(vector), limit))
        matches = self._matches if self._matches is not None else [
            (vector_id, 0.9) for vector_id in self.vectors
        ]
        return matches[:limit]

    def fetch(self, ids: Sequence[str]) -> dict[str, tuple[float, ...]]:
        if self.fail:
            raise VectorStoreError("pinecone_fetch_failed: simulated")
        self.fetch_calls.append(list(ids))
        wanted = set(ids)
        return {k: v for k, v in self.vectors.items() if k in wanted}


def _write_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "00940345.md").write_text(_WIKI_PAGE, encoding="utf-8")
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
    return wiki


def _enable_semantic_search(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-pinecone-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    get_settings.cache_clear()


def _use_store(monkeypatch, store: _FakeVectorStore) -> None:
    monkeypatch.setattr(
        "app.retrieval.wiki_vector_index.get_vector_store",
        lambda **_kwargs: store,
    )


def _stub_query_embedding(monkeypatch, vector: tuple[float, ...] = (1.0, 0.0)) -> None:
    monkeypatch.setattr(
        "app.retrieval.wiki_vector_index.embed_query_cached",
        lambda *_args, **_kwargs: vector,
    )


def _chunk(section_title: str = "Description") -> WikiChunk:
    return WikiChunk(
        source_file="courses/009-dds/00940345.md",
        page_title="Discrete Math",
        section_title=section_title,
        heading_path=("Discrete Math", section_title),
        content="Students learn discrete mathematics for DDS.",
    )


# -- id scheme -----------------------------------------------------------


def test_vector_id_is_ascii_for_hebrew_section_titles():
    """Pinecone rejects non-ASCII record ids, and this corpus is mostly Hebrew.

    The retired on-disk cache keyed chunks by
    `source_file::section_title::digest`, which is not a legal id here.
    """
    vector_id = chunk_vector_id(_chunk(_HEBREW_SECTION))
    assert vector_id.isascii()
    assert len(vector_id) == 64
    assert len(vector_id) <= 512


def test_vector_id_is_stable_across_calls():
    assert chunk_vector_id(_chunk()) == chunk_vector_id(_chunk())


def test_vector_id_changes_when_content_changes():
    """Content-addressing is what lets a reindex detect and prune stale vectors."""
    original = _chunk()
    edited = WikiChunk(
        source_file=original.source_file,
        page_title=original.page_title,
        section_title=original.section_title,
        heading_path=original.heading_path,
        content=original.content + " Now with an extra sentence.",
    )
    assert chunk_vector_id(original) != chunk_vector_id(edited)


def test_vector_ids_differ_across_sections_of_one_page():
    assert chunk_vector_id(_chunk("Description")) != chunk_vector_id(_chunk("Sources"))


# -- metadata ------------------------------------------------------------


def test_metadata_omits_empty_values():
    """Pinecone rejects null metadata values outright."""
    metadata = chunk_metadata(_chunk())
    assert "catalog_year" not in metadata
    assert "faculty" not in metadata
    assert "course_numbers" not in metadata
    assert all(value is not None for value in metadata.values())


def test_metadata_carries_the_readable_identity_dropped_from_the_id():
    metadata = chunk_metadata(_chunk(_HEBREW_SECTION))
    assert metadata["source_file"] == "courses/009-dds/00940345.md"
    assert metadata["section_title"] == _HEBREW_SECTION
    assert metadata["page_title"] == "Discrete Math"


def test_metadata_stringifies_course_number_lists():
    chunk = WikiChunk(
        source_file="courses/x.md",
        page_title="X",
        section_title="Description",
        heading_path=("X",),
        content="body",
        course_numbers_mentioned=("00940345", "00440105"),
        catalog_year=2025,
    )
    metadata = chunk_metadata(chunk)
    assert metadata["course_numbers"] == ["00940345", "00440105"]
    assert metadata["catalog_year"] == 2025


# -- query path ----------------------------------------------------------


def test_query_returns_empty_when_pinecone_unconfigured(tmp_path, monkeypatch):
    """The BM25-only degradation path — no key means no semantic hits, no error."""
    wiki = _write_wiki(tmp_path)
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()
    assert query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=3) == []


def test_query_returns_empty_when_embeddings_unconfigured(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("PINECONE_API_KEY", "test-pinecone-key")
    get_settings.cache_clear()
    assert query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=3) == []


def test_query_hydrates_hits_from_disk(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    assert chunks
    target = chunks[0]
    store = _FakeVectorStore(matches=[(chunk_vector_id(target), 0.87)])
    _use_store(monkeypatch, store)
    _stub_query_embedding(monkeypatch)

    results = query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=3)

    assert len(results) == 1
    chunk, score = results[0]
    assert chunk.page_title == target.page_title
    assert chunk.content == target.content
    assert score == pytest.approx(0.87)


def test_query_drops_vectors_whose_chunk_no_longer_exists(tmp_path, monkeypatch):
    """A stale Pinecone id must not crash or fabricate a chunk — just vanish."""
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    live_id = chunk_vector_id(chunks[0])
    store = _FakeVectorStore(matches=[(live_id, 0.9), ("deadbeef" * 8, 0.8)])
    _use_store(monkeypatch, store)
    _stub_query_embedding(monkeypatch)

    results = query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=5)

    assert len(results) == 1
    assert results[0][0].page_title == chunks[0].page_title


def test_query_degrades_to_empty_when_store_fails(tmp_path, monkeypatch):
    """Pinecone being down degrades retrieval to BM25 — it does not raise."""
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    _use_store(monkeypatch, _FakeVectorStore(fail=True))
    _stub_query_embedding(monkeypatch)

    assert query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=3) == []


def test_query_skipped_when_embedding_returns_nothing(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    store = _FakeVectorStore()
    _use_store(monkeypatch, store)
    monkeypatch.setattr(
        "app.retrieval.wiki_vector_index.embed_query_cached",
        lambda *_args, **_kwargs: None,
    )

    assert query_semantic_candidates(query="discrete", wiki_root=str(wiki), limit=3) == []
    assert store.query_calls == []


# -- fetch path (reranker) ----------------------------------------------


def test_fetch_chunk_vectors_uses_one_batched_call(tmp_path, monkeypatch):
    """The reranker must not make a round trip per candidate chunk."""
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    assert len(chunks) >= 2
    store = _FakeVectorStore({chunk_vector_id(c): (1.0, 0.0) for c in chunks})
    _use_store(monkeypatch, store)

    vectors = fetch_chunk_vectors(chunks, settings=get_settings())

    assert len(store.fetch_calls) == 1
    assert len(store.fetch_calls[0]) == len(chunks)
    assert set(vectors) == {chunk_vector_id(c) for c in chunks}


def test_fetch_chunk_vectors_empty_when_disabled(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    assert fetch_chunk_vectors(chunks, settings=get_settings()) == {}


def test_fetch_chunk_vectors_empty_on_store_failure(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _enable_semantic_search(monkeypatch)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    _use_store(monkeypatch, _FakeVectorStore(fail=True))
    assert fetch_chunk_vectors(chunks, settings=get_settings()) == {}


def test_fetch_chunk_vectors_empty_for_no_chunks(monkeypatch):
    _enable_semantic_search(monkeypatch)
    assert fetch_chunk_vectors([], settings=get_settings()) == {}


# -- cost estimates ------------------------------------------------------


def test_estimate_index_build_cost_without_api(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_PATH", str(wiki))
    get_settings.cache_clear()
    estimate = estimate_index_build_cost(wiki_root=str(wiki))
    assert estimate["chunkCount"] >= 1
    assert estimate["estimatedInputTokens"] > 0


def test_estimate_query_embedding_cost():
    estimate = estimate_query_embedding_cost(query_count=331)
    assert estimate["estimatedInputTokens"] == 331 * 12
