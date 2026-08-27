"""Write path: populate and prune the Pinecone wiki index.

Unlike the read path in `wiki_vector_index`, everything here fails loudly --
a reindex that half-succeeds silently is worse than one that stops.

Two ways in:

* `reindex_wiki` embeds every chunk fresh (costs one embedding API pass over
  the corpus).
* `backfill_from_legacy_cache` reuses the vectors already sitting in the old
  on-disk `.compact.pkl.gz`, so the migration costs nothing. Same model, same
  content-addressed chunks -- only the id scheme changes.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import pickle
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.retrieval.embedding_service import embed_documents
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks
from app.retrieval.reranker import embedding_text
from app.retrieval.vector_store import (
    PineconeVectorStore,
    VectorRecord,
    VectorStoreError,
    get_vector_store,
)
from app.retrieval.wiki_vector_index import (
    canonical_wiki_root,
    chunk_metadata,
    chunk_vector_id,
)

logger = logging.getLogger(__name__)

_LEGACY_CACHE_VERSION = 2


def _require_store(settings: Settings) -> PineconeVectorStore:
    store = get_vector_store(settings=settings)
    if store is None:
        raise VectorStoreError(
            "pinecone_not_configured: set PINECONE_API_KEY and PINECONE_INDEX_NAME"
        )
    return store


def _legacy_cache_key(chunk: WikiChunk) -> str:
    """The on-disk index's old composite key, kept only to map it forward.

    Was `source_file::section_title::digest[:16]` -- not a legal Pinecone id
    because section titles are Hebrew. See `chunk_vector_id`.
    """
    digest = hashlib.sha256(
        f"{chunk.source_file}|{chunk.section_title}|{chunk.content}".encode("utf-8")
    ).hexdigest()
    return f"{chunk.source_file}::{chunk.section_title}::{digest[:16]}"


def _compact_cache_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.compact.pkl.gz")


def _records_for_chunks(
    chunks: Sequence[WikiChunk],
    vectors: Sequence[Sequence[float]],
) -> list[VectorRecord]:
    return [
        VectorRecord(
            id=chunk_vector_id(chunk),
            vector=tuple(float(value) for value in vector),
            metadata=chunk_metadata(chunk),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def _prune_stale(
    store: PineconeVectorStore,
    *,
    live_ids: set[str],
) -> int:
    """Delete vectors whose chunk no longer exists on disk.

    Content-addressed ids mean an edited chunk lands under a new id, so
    without this the namespace accumulates orphans that can still be returned
    by a query (and then get dropped during hydration).
    """
    stale = [
        vector_id for vector_id in store.list_ids() if vector_id not in live_ids
    ]
    if stale:
        store.delete(stale)
        logger.info("wiki_index_pruned_stale_vectors", extra={"count": len(stale)})
    return len(stale)


def reindex_wiki(
    *,
    wiki_root: str,
    settings: Settings | None = None,
    prune: bool = True,
    on_batch_embedded: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Embed every chunk and upsert it to Pinecone."""
    cfg = settings or get_settings()
    if not cfg.embeddings_available():
        raise VectorStoreError("embedding_api_key_missing")
    store = _require_store(cfg)
    store.ensure_index()

    root = canonical_wiki_root(wiki_root)
    chunks = list(load_wiki_chunks(root))
    if not chunks:
        raise VectorStoreError(f"no_wiki_chunks_found: {root}")

    texts = [embedding_text(chunk) for chunk in chunks]
    batch_size = max(1, int(cfg.embedding_index_batch_size or 64))
    total_batches = (len(texts) + batch_size - 1) // batch_size
    upserted = 0

    for batch_index, start in enumerate(range(0, len(texts), batch_size), start=1):
        window = slice(start, start + batch_size)
        vectors = embed_documents(texts[window], settings=cfg)
        if not vectors:
            raise VectorStoreError(f"embedding_failed_at_batch: {batch_index}")
        upserted += store.upsert(_records_for_chunks(chunks[window], vectors))
        if on_batch_embedded is not None:
            on_batch_embedded(batch_index, total_batches)

    pruned = (
        _prune_stale(store, live_ids={chunk_vector_id(chunk) for chunk in chunks})
        if prune
        else 0
    )
    return {
        "status": "ok",
        "source": "embedded",
        "wikiRoot": root,
        "chunkCount": len(chunks),
        "upserted": upserted,
        "pruned": pruned,
        "model": cfg.resolved_embedding_model(),
        "indexName": cfg.resolved_pinecone_index_name(),
        "namespace": cfg.resolved_pinecone_namespace(),
    }


def _iter_legacy_vectors(
    cache_path: Path,
    *,
    expected_model: str,
) -> Iterator[tuple[str, tuple[float, ...]]]:
    compact_path = _compact_cache_path(cache_path)
    if not compact_path.is_file():
        raise VectorStoreError(f"legacy_cache_not_found: {compact_path}")
    with gzip.open(compact_path, "rb") as handle:
        payload = pickle.load(handle)  # nosec B301 - our own cache file
    if not isinstance(payload, dict):
        raise VectorStoreError("legacy_cache_malformed")
    if int(payload.get("version") or 0) != _LEGACY_CACHE_VERSION:
        raise VectorStoreError(f"legacy_cache_version_unsupported: {payload.get('version')}")
    stored_model = str(payload.get("model") or "")
    if stored_model != expected_model:
        raise VectorStoreError(
            f"legacy_cache_model_mismatch: cache={stored_model} expected={expected_model}"
        )
    keys = payload.get("keys")
    vectors = payload.get("vectors")
    if not isinstance(keys, list) or not isinstance(vectors, list):
        raise VectorStoreError("legacy_cache_missing_keys_or_vectors")
    for key, vector in zip(keys, vectors, strict=True):
        yield str(key), tuple(float(value) for value in vector)


def backfill_from_legacy_cache(
    *,
    cache_path: Path,
    wiki_root: str,
    settings: Settings | None = None,
    prune: bool = True,
) -> dict[str, Any]:
    """Upload the existing on-disk vectors to Pinecone without re-embedding.

    The old cache keys the same content under a different (non-ASCII) scheme,
    so chunks are re-read from disk to map old key -> new id. A chunk whose
    content changed since that cache was written simply won't map, and is
    reported as `skipped` rather than uploaded under a stale vector.
    """
    cfg = settings or get_settings()
    store = _require_store(cfg)
    store.ensure_index()

    root = canonical_wiki_root(wiki_root)
    chunks = list(load_wiki_chunks(root))
    if not chunks:
        raise VectorStoreError(f"no_wiki_chunks_found: {root}")
    chunk_by_legacy_key = {_legacy_cache_key(chunk): chunk for chunk in chunks}

    expected_dimension = int(cfg.pinecone_dimension)
    records: list[VectorRecord] = []
    skipped = 0
    for legacy_key, vector in _iter_legacy_vectors(
        cache_path,
        expected_model=cfg.resolved_embedding_model(),
    ):
        chunk = chunk_by_legacy_key.get(legacy_key)
        if chunk is None:
            skipped += 1
            continue
        if len(vector) != expected_dimension:
            raise VectorStoreError(
                f"legacy_vector_dimension_mismatch: got={len(vector)} "
                f"expected={expected_dimension}"
            )
        records.append(
            VectorRecord(
                id=chunk_vector_id(chunk),
                vector=vector,
                metadata=chunk_metadata(chunk),
            )
        )

    if not records:
        raise VectorStoreError("legacy_cache_produced_no_records")

    upserted = store.upsert(records)
    pruned = (
        _prune_stale(store, live_ids={record.id for record in records})
        if prune
        else 0
    )
    return {
        "status": "ok",
        "source": "legacy_cache",
        "wikiRoot": root,
        "cachePath": str(_compact_cache_path(cache_path)),
        "chunkCount": len(chunks),
        "upserted": upserted,
        "skippedStaleCacheEntries": skipped,
        "pruned": pruned,
        "model": cfg.resolved_embedding_model(),
        "indexName": cfg.resolved_pinecone_index_name(),
        "namespace": cfg.resolved_pinecone_namespace(),
    }


def verify_index(
    *,
    wiki_root: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compare what Pinecone holds against what the wiki on disk expects."""
    cfg = settings or get_settings()
    store = _require_store(cfg)
    root = canonical_wiki_root(wiki_root)
    chunks = list(load_wiki_chunks(root))
    expected_ids = {chunk_vector_id(chunk) for chunk in chunks}
    remote_count = store.count()
    sample = list(expected_ids)[:100]
    present = store.fetch(sample) if sample else {}
    return {
        "ok": bool(chunks) and remote_count > 0 and len(present) == len(sample),
        "wikiRoot": root,
        "indexName": cfg.resolved_pinecone_index_name(),
        "namespace": cfg.resolved_pinecone_namespace(),
        "chunkCountOnDisk": len(chunks),
        "vectorCountInPinecone": remote_count,
        "sampleChecked": len(sample),
        "samplePresent": len(present),
        "model": cfg.resolved_embedding_model(),
    }


__all__ = [
    "backfill_from_legacy_cache",
    "reindex_wiki",
    "verify_index",
]
