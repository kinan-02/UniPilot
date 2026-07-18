"""Read path for wiki chunk embeddings, backed by Pinecone.

Vectors live in Pinecone; chunk *content* is still parsed from the markdown
on disk by `load_wiki_chunks`. That split is deliberate rather than a
half-migration: `AcademicGraphEngine.search_wiki` reads every chunk off disk
for the BM25 half of its candidate pool, so the wiki mount is a hard
dependency of retrieval no matter where vectors live. Storing chunk text in
Pinecone metadata as well would buy nothing and add a second source of truth
that can drift from the markdown.

Both entry points here degrade to empty rather than raising -- retrieval then
falls back to BM25-only, the same path that already ran whenever
`EMBEDDING_API_KEY` was unset. The reindex CLI (`wiki_index_sync`) is the one
place Pinecone failures are surfaced loudly.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings
from app.retrieval.embedding_service import embed_query_cached
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks
from app.retrieval.reranker import embedding_text
from app.retrieval.vector_store import (
    VectorStoreError,
    get_vector_store,
    reset_vector_store_cache,
)
from app.retrieval.wiki_paths import resolve_wiki_root

logger = logging.getLogger(__name__)


def canonical_wiki_root(wiki_root: str) -> str:
    """Normalize wiki root so chunk identity stays stable across relative paths."""
    return resolve_wiki_root(wiki_root)


def chunk_vector_id(chunk: WikiChunk) -> str:
    """Stable, content-addressed Pinecone id for a chunk.

    Must be pure ASCII -- Pinecone rejects non-ASCII record ids, and this
    corpus is largely Hebrew (section titles like `## פרטי הקורס בעברית`), so
    the readable `source_file::section_title::` prefix the on-disk cache used
    is not a legal id here. The human-readable parts move to metadata.

    Content-addressing means an edited chunk gets a new id, which is what
    lets a reindex detect and prune what went stale.
    """
    digest = hashlib.sha256(
        f"{chunk.source_file}|{chunk.section_title}|{chunk.content}".encode("utf-8")
    ).hexdigest()
    return digest


def chunk_metadata(chunk: WikiChunk) -> dict[str, Any]:
    """Filterable metadata for one chunk.

    Content is deliberately absent (see module docstring). Pinecone rejects
    null metadata values, so empty fields are omitted rather than sent as
    None.
    """
    raw: dict[str, Any] = {
        "source_file": chunk.source_file,
        "page_title": chunk.page_title,
        "section_title": chunk.section_title,
        "language": chunk.language,
        "catalog_year": chunk.catalog_year,
        "faculty": chunk.faculty,
        "degree_program": chunk.degree_program,
        "track": chunk.track,
        "course_numbers": list(chunk.course_numbers_mentioned or ()),
    }
    metadata: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        elif isinstance(value, list):
            metadata[key] = [str(item) for item in value]
        else:
            metadata[key] = str(value)
    return metadata


@lru_cache(maxsize=2)
def _chunk_by_vector_id(wiki_root: str) -> dict[str, WikiChunk]:
    """Id -> chunk map used to hydrate Pinecone hits from the markdown on disk.

    `load_wiki_chunks` is itself `lru_cache`d, so this only pays the dict
    build. Cleared by `reset_wiki_vector_index_runtime_cache`.
    """
    return {chunk_vector_id(chunk): chunk for chunk in load_wiki_chunks(wiki_root)}


def reset_wiki_vector_index_runtime_cache() -> None:
    _chunk_by_vector_id.cache_clear()
    reset_vector_store_cache()


def _query_vector(query: str, cfg: Settings) -> tuple[float, ...] | None:
    return embed_query_cached(
        query,
        cfg.resolved_embedding_api_key(),
        cfg.resolved_embedding_base_url(),
        cfg.resolved_embedding_model(),
    )


def query_semantic_candidates(
    *,
    query: str,
    wiki_root: str,
    limit: int,
    settings: Settings | None = None,
) -> list[tuple[WikiChunk, float]]:
    """Top-`limit` chunks by cosine similarity, hydrated from disk.

    Returns `[]` -- never raises -- when embeddings or Pinecone are
    unavailable, so callers degrade to keyword search.
    """
    cfg = settings or get_settings()
    if not cfg.wiki_vector_index_enabled() or limit <= 0:
        return []
    store = get_vector_store(settings=cfg)
    if store is None:
        return []

    query_vector = _query_vector(query, cfg)
    if not query_vector:
        return []

    try:
        matches = store.query(list(query_vector), limit=limit)
    except VectorStoreError:
        logger.exception("wiki_semantic_query_failed")
        return []

    chunk_by_id = _chunk_by_vector_id(canonical_wiki_root(wiki_root))
    hits: list[tuple[WikiChunk, float]] = []
    for vector_id, score in matches:
        chunk = chunk_by_id.get(vector_id)
        # A miss means Pinecone holds a vector for content that has since been
        # edited or deleted on disk. Dropping it is correct -- the reindex
        # prunes these -- and matches how the old cache silently skipped keys
        # with no surviving chunk.
        if chunk is not None:
            hits.append((chunk, score))
    if len(hits) < len(matches):
        logger.warning(
            "wiki_semantic_stale_vectors_skipped",
            extra={"matched": len(matches), "hydrated": len(hits)},
        )
    return hits


def fetch_chunk_vectors(
    chunks: Sequence[WikiChunk],
    *,
    settings: Settings | None = None,
) -> dict[str, tuple[float, ...]]:
    """Vectors for an arbitrary candidate set, keyed by `chunk_vector_id`.

    One batched round trip for the whole set. The reranker needs this because
    its candidates include BM25-only hits that never appeared in a
    corpus-wide top-K, and because `retrieve_page_chunks` reranks the sections
    of a single page -- neither of which a top-K query alone can score.

    Returns `{}` rather than raising, so reranking silently drops to its
    keyword component.
    """
    cfg = settings or get_settings()
    if not cfg.wiki_vector_index_enabled() or not chunks:
        return {}
    store = get_vector_store(settings=cfg)
    if store is None:
        return {}
    ids = [chunk_vector_id(chunk) for chunk in chunks]
    try:
        return store.fetch(ids)
    except VectorStoreError:
        logger.exception("wiki_vector_fetch_failed")
        return {}


def score_page_scoped_chunks(
    chunks: Sequence[WikiChunk],
    *,
    query: str,
    settings: Settings | None = None,
) -> dict[str, float]:
    """Similarity scores for a page-scoped candidate set, keyed by vector id.

    One metadata-filtered Pinecone query that returns scores directly, instead
    of fetching every candidate's vector to recompute cosine locally. Measured
    on a 7-section page: 167ms vs 345ms, and it halves the read units.

    CALLER CONTRACT: `chunks` must be *every* indexed chunk of the source
    files it spans (which is what `retrieve_page_chunks` produces -- it takes
    all chunks whose stem matches the slug). If it were only a subset, `top_k`
    would let Pinecone return that file's other sections instead, scoring
    non-candidates and leaving real candidates unscored. `fetch_chunk_vectors`
    is the correct choice for an arbitrary candidate set.

    Returns `{}` rather than raising, so reranking drops to its keyword
    component.
    """
    cfg = settings or get_settings()
    if not cfg.wiki_vector_index_enabled() or not chunks:
        return {}
    store = get_vector_store(settings=cfg)
    if store is None:
        return {}

    query_vector = _query_vector(query, cfg)
    if not query_vector:
        return {}

    source_files = sorted({chunk.source_file for chunk in chunks if chunk.source_file})
    if not source_files:
        return {}

    try:
        matches = store.query(
            list(query_vector),
            limit=len(chunks),
            metadata_filter={"source_file": {"$in": source_files}},
        )
    except VectorStoreError:
        logger.exception("wiki_page_scoped_query_failed")
        return {}
    return {vector_id: score for vector_id, score in matches}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_index_build_cost(
    *,
    wiki_root: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    chunks = list(load_wiki_chunks(canonical_wiki_root(wiki_root)))
    texts = [embedding_text(chunk) for chunk in chunks]
    total_tokens = sum(_estimate_tokens(text) for text in texts)
    batch_size = max(1, int(cfg.embedding_index_batch_size or 64))
    return {
        "wikiRoot": canonical_wiki_root(wiki_root),
        "chunkCount": len(chunks),
        "estimatedInputTokens": total_tokens,
        "embeddingModel": cfg.resolved_embedding_model(),
        "batchCount": (len(texts) + batch_size - 1) // batch_size if texts else 0,
        "notes": "One-time index build. Rebuild only when wiki content or model changes.",
    }


def estimate_query_embedding_cost(
    *,
    query_count: int,
    avg_query_tokens: int = 12,
) -> dict[str, Any]:
    return {
        "queryCount": query_count,
        "estimatedInputTokens": query_count * avg_query_tokens,
        "notes": "Per-query cost is the query embedding only; chunk vectors are stored.",
    }


__all__ = [
    "canonical_wiki_root",
    "chunk_metadata",
    "chunk_vector_id",
    "estimate_index_build_cost",
    "estimate_query_embedding_cost",
    "fetch_chunk_vectors",
    "query_semantic_candidates",
    "reset_wiki_vector_index_runtime_cache",
    "score_page_scoped_chunks",
]
