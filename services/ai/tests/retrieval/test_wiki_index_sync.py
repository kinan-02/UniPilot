"""Tests for the Pinecone write path: backfill, reindex, prune (no network)."""

from __future__ import annotations

import gzip
import hashlib
import pickle
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from app.config import get_settings
from app.retrieval.obsidian_wiki_indexer import (
    WikiChunk,
    load_wiki_chunks,
    reset_wiki_index_cache,
)
from app.retrieval.vector_store import PineconeVectorStore, VectorRecord, VectorStoreError
from app.retrieval.wiki_index_sync import backfill_from_legacy_cache, reindex_wiki, verify_index
from app.retrieval.wiki_vector_index import chunk_vector_id, reset_wiki_vector_index_runtime_cache

_MODEL = "MB5R2CF-azure/text-embedding-3-small"
_DIMENSION = 4

_WIKI_PAGE = """---
title: Discrete Math
---
# Discrete Math
## Description
Students learn discrete mathematics for DDS in this section of the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
## פרטי הקורס בעברית
תיאור הקורס בעברית עם מספיק תוכן כדי להיחשב מקטע לאינדוקס. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page. Additional explanatory sentence providing enough body text that this section is indexed on its own rather than merged into the page.
"""


class _RecordingStore:
    def __init__(self, *, existing_ids: list[str] | None = None) -> None:
        self.upserted: list[VectorRecord] = []
        self.deleted: list[str] = []
        self.existing_ids = list(existing_ids or [])
        self.ensure_index_calls = 0

    def ensure_index(self) -> bool:
        self.ensure_index_calls += 1
        return False

    def upsert(self, records) -> int:
        batch = list(records)
        self.upserted.extend(batch)
        return len(batch)

    def delete(self, ids: Sequence[str]) -> None:
        self.deleted.extend(ids)

    def list_ids(self) -> Iterator[str]:
        yield from self.existing_ids

    def fetch(self, ids: Sequence[str]) -> dict[str, tuple[float, ...]]:
        wanted = set(ids)
        return {i: (1.0,) * _DIMENSION for i in self.existing_ids if i in wanted}

    def count(self) -> int:
        return len(self.existing_ids)


def _write_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "00940345.md").write_text(_WIKI_PAGE, encoding="utf-8")
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
    return wiki


def _legacy_key(chunk: WikiChunk) -> str:
    digest = hashlib.sha256(
        f"{chunk.source_file}|{chunk.section_title}|{chunk.content}".encode("utf-8")
    ).hexdigest()
    return f"{chunk.source_file}::{chunk.section_title}::{digest[:16]}"


def _write_legacy_cache(
    tmp_path: Path,
    chunks: Sequence[WikiChunk],
    *,
    model: str = _MODEL,
    version: int = 2,
    dimension: int = _DIMENSION,
    extra_keys: Sequence[str] = (),
) -> Path:
    cache_path = tmp_path / "wiki_embedding_index.json"
    compact = cache_path.with_name(f"{cache_path.stem}.compact.pkl.gz")
    keys = [_legacy_key(chunk) for chunk in chunks] + list(extra_keys)
    payload = {
        "version": version,
        "wikiRoot": str(tmp_path / "wiki"),
        "model": model,
        "keys": keys,
        "vectors": [tuple(0.5 for _ in range(dimension)) for _ in keys],
    }
    with gzip.open(compact, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return cache_path


def _configure(monkeypatch, store: _RecordingStore) -> None:
    monkeypatch.setenv("PINECONE_API_KEY", "test-pinecone-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    monkeypatch.setenv("PINECONE_DIMENSION", str(_DIMENSION))
    monkeypatch.setenv("EMBEDDING_MODEL", _MODEL)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.retrieval.wiki_index_sync.get_vector_store",
        lambda **_kwargs: store,
    )


# -- backfill ------------------------------------------------------------


def test_backfill_maps_legacy_keys_to_ascii_ids(tmp_path, monkeypatch):
    """The whole point of the migration path: reuse vectors, re-key them."""
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    assert len(chunks) >= 2
    cache_path = _write_legacy_cache(tmp_path, chunks)
    store = _RecordingStore()
    _configure(monkeypatch, store)

    report = backfill_from_legacy_cache(
        cache_path=cache_path,
        wiki_root=str(wiki),
        settings=get_settings(),
    )

    assert report["status"] == "ok"
    assert report["source"] == "legacy_cache"
    assert report["upserted"] == len(chunks)
    assert {r.id for r in store.upserted} == {chunk_vector_id(c) for c in chunks}
    assert all(r.id.isascii() for r in store.upserted)
    assert store.ensure_index_calls == 1


def test_backfill_attaches_metadata(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks)
    store = _RecordingStore()
    _configure(monkeypatch, store)

    backfill_from_legacy_cache(
        cache_path=cache_path,
        wiki_root=str(wiki),
        settings=get_settings(),
    )

    assert all("source_file" in r.metadata for r in store.upserted)
    assert all("section_title" in r.metadata for r in store.upserted)


def test_backfill_skips_cache_entries_with_no_surviving_chunk(tmp_path, monkeypatch):
    """Content edited since the cache was written must not upload a stale vector."""
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(
        tmp_path,
        chunks,
        extra_keys=("courses/gone.md::Removed::0123456789abcdef",),
    )
    store = _RecordingStore()
    _configure(monkeypatch, store)

    report = backfill_from_legacy_cache(
        cache_path=cache_path,
        wiki_root=str(wiki),
        settings=get_settings(),
    )

    assert report["skippedStaleCacheEntries"] == 1
    assert report["upserted"] == len(chunks)


def test_backfill_prunes_ids_absent_from_disk(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks)
    orphan = "f" * 64
    store = _RecordingStore(existing_ids=[orphan, chunk_vector_id(chunks[0])])
    _configure(monkeypatch, store)

    report = backfill_from_legacy_cache(
        cache_path=cache_path,
        wiki_root=str(wiki),
        settings=get_settings(),
    )

    assert store.deleted == [orphan]
    assert report["pruned"] == 1


def test_backfill_respects_no_prune(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks)
    store = _RecordingStore(existing_ids=["f" * 64])
    _configure(monkeypatch, store)

    report = backfill_from_legacy_cache(
        cache_path=cache_path,
        wiki_root=str(wiki),
        settings=get_settings(),
        prune=False,
    )

    assert store.deleted == []
    assert report["pruned"] == 0


def test_backfill_rejects_model_mismatch(tmp_path, monkeypatch):
    """Vectors from another model are silently meaningless — fail loudly instead."""
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks, model="some-other-model")
    _configure(monkeypatch, _RecordingStore())

    with pytest.raises(VectorStoreError, match="legacy_cache_model_mismatch"):
        backfill_from_legacy_cache(
            cache_path=cache_path,
            wiki_root=str(wiki),
            settings=get_settings(),
        )


def test_backfill_rejects_dimension_mismatch(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks, dimension=_DIMENSION + 1)
    _configure(monkeypatch, _RecordingStore())

    with pytest.raises(VectorStoreError, match="legacy_vector_dimension_mismatch"):
        backfill_from_legacy_cache(
            cache_path=cache_path,
            wiki_root=str(wiki),
            settings=get_settings(),
        )


def test_backfill_rejects_unsupported_cache_version(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks, version=1)
    _configure(monkeypatch, _RecordingStore())

    with pytest.raises(VectorStoreError, match="legacy_cache_version_unsupported"):
        backfill_from_legacy_cache(
            cache_path=cache_path,
            wiki_root=str(wiki),
            settings=get_settings(),
        )


def test_backfill_reports_missing_cache_file(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _configure(monkeypatch, _RecordingStore())

    with pytest.raises(VectorStoreError, match="legacy_cache_not_found"):
        backfill_from_legacy_cache(
            cache_path=tmp_path / "absent.json",
            wiki_root=str(wiki),
            settings=get_settings(),
        )


def test_backfill_requires_pinecone_configured(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    cache_path = _write_legacy_cache(tmp_path, chunks)
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(VectorStoreError, match="pinecone_not_configured"):
        backfill_from_legacy_cache(
            cache_path=cache_path,
            wiki_root=str(wiki),
            settings=get_settings(),
        )


# -- reindex -------------------------------------------------------------


def test_reindex_requires_embedding_key(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _configure(monkeypatch, _RecordingStore())
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(VectorStoreError, match="embedding_api_key_missing"):
        reindex_wiki(wiki_root=str(wiki), settings=get_settings())


def test_reindex_embeds_and_upserts_every_chunk(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    store = _RecordingStore()
    _configure(monkeypatch, store)
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.retrieval.wiki_index_sync.embed_documents",
        lambda texts, **_kwargs: [[0.25] * _DIMENSION for _ in texts],
    )

    report = reindex_wiki(wiki_root=str(wiki), settings=get_settings())

    assert report["status"] == "ok"
    assert report["source"] == "embedded"
    assert report["upserted"] == len(chunks)
    assert {r.id for r in store.upserted} == {chunk_vector_id(c) for c in chunks}


def test_reindex_fails_loudly_when_embedding_returns_nothing(tmp_path, monkeypatch):
    """A partial index that looks complete is worse than a failed build."""
    wiki = _write_wiki(tmp_path)
    _configure(monkeypatch, _RecordingStore())
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.retrieval.wiki_index_sync.embed_documents",
        lambda _texts, **_kwargs: None,
    )

    with pytest.raises(VectorStoreError, match="embedding_failed_at_batch"):
        reindex_wiki(wiki_root=str(wiki), settings=get_settings())


# -- verify --------------------------------------------------------------


def test_verify_reports_disk_and_remote_counts(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    chunks = list(load_wiki_chunks(str(wiki.resolve())))
    store = _RecordingStore(existing_ids=[chunk_vector_id(c) for c in chunks])
    _configure(monkeypatch, store)

    report = verify_index(wiki_root=str(wiki), settings=get_settings())

    assert report["ok"] is True
    assert report["chunkCountOnDisk"] == len(chunks)
    assert report["vectorCountInPinecone"] == len(chunks)


def test_verify_flags_an_empty_index(tmp_path, monkeypatch):
    wiki = _write_wiki(tmp_path)
    _configure(monkeypatch, _RecordingStore(existing_ids=[]))

    report = verify_index(wiki_root=str(wiki), settings=get_settings())

    assert report["ok"] is False
    assert report["vectorCountInPinecone"] == 0


class _FakeStats:
    def __init__(self, namespaces: dict[str, int], total: int) -> None:
        self.namespaces = {
            name: type("NS", (), {"vector_count": count})()
            for name, count in namespaces.items()
        }
        self.total_vector_count = total


def _store_with_stats(stats: _FakeStats, namespace: str) -> PineconeVectorStore:
    store = PineconeVectorStore(
        api_key="test-key",
        index_name="test-index",
        namespace=namespace,
    )
    store._index = type("Idx", (), {"describe_index_stats": lambda _self, **_kw: stats})()
    return store


def test_count_reports_zero_for_a_configured_namespace_that_is_empty():
    """Must not report another namespace's vectors as this one's.

    Falling back to the index-wide total here would make a namespace typo
    look like a populated index -- the exact moment the number matters.
    """
    stats = _FakeStats({"other": 500}, total=500)
    assert _store_with_stats(stats, namespace="mine").count() == 0


def test_count_uses_the_index_total_only_when_no_namespace_is_configured():
    stats = _FakeStats({"other": 500}, total=500)
    assert _store_with_stats(stats, namespace="").count() == 500


def test_count_reads_the_configured_namespace_when_present():
    stats = _FakeStats({"mine": 12586, "other": 500}, total=13086)
    assert _store_with_stats(stats, namespace="mine").count() == 12586
