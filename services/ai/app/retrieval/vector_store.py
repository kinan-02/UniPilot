"""Pinecone-backed vector store for wiki chunk embeddings.

Replaces the previous on-disk index (a 47MB pickle under `/app/data/cache`
that no compose volume backed, so every container rebuild wiped it and forced
a full re-embed of ~12.5k chunks on next boot).

Failure policy is split deliberately:

* This module RAISES `VectorStoreError` -- the reindex CLI must fail loudly
  rather than silently write a partial index.
* `wiki_vector_index` catches and returns empty, degrading retrieval to
  BM25-only. That is the same graceful path that already ran whenever
  `EMBEDDING_API_KEY` was unset.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Pinecone caps upserts at 1000 vectors / 2MB per request. 1536 float32 dims
# is ~6KB per record before metadata, so 2MB binds well before 1000 records --
# 200 keeps each request comfortably under it.
_UPSERT_BATCH_SIZE = 200
# `fetch` takes ids in the query string; keep batches small enough that the
# URL stays well inside typical proxy limits (64 hex chars per id).
_FETCH_BATCH_SIZE = 100


class VectorStoreError(RuntimeError):
    """Raised when a vector store operation fails irrecoverably."""


@dataclass(frozen=True)
class VectorRecord:
    """One chunk's embedding plus the metadata Pinecone can filter on."""

    id: str
    vector: tuple[float, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    """Minimal surface the retrieval path needs from a vector backend."""

    def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[str, float]]:
        """Top-`limit` (id, score) pairs by cosine similarity."""
        ...

    def fetch(self, ids: Sequence[str]) -> dict[str, tuple[float, ...]]:
        """Vectors for known ids. Missing ids are simply absent from the result."""
        ...

    def upsert(self, records: Iterable[VectorRecord]) -> int:
        """Write records; returns how many were sent."""
        ...

    def delete(self, ids: Sequence[str]) -> None: ...

    def list_ids(self) -> Iterator[str]: ...

    def count(self) -> int: ...


class PineconeVectorStore:
    """`VectorStore` over one Pinecone serverless index + namespace."""

    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        namespace: str = "",
        timeout_seconds: float = 10.0,
        dimension: int = 1536,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        if not api_key:
            raise VectorStoreError("pinecone_api_key_missing")
        if not index_name:
            raise VectorStoreError("pinecone_index_name_missing")
        self._api_key = api_key
        self._index_name = index_name
        self._namespace = namespace
        self._timeout = timeout_seconds
        self._dimension = dimension
        self._cloud = cloud
        self._region = region
        self._client: Any = None
        self._index: Any = None

    # -- connection ------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            from pinecone import Pinecone

            # `timeout` bounds every request made through this client. The
            # default is 30s; we set it lower because retrieval runs inside a
            # turn that has its own deadline.
            self._client = Pinecone(api_key=self._api_key, timeout=self._timeout)
        return self._client

    def _get_index(self) -> Any:
        if self._index is None:
            try:
                self._index = self._get_client().Index(self._index_name)
            except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
                raise VectorStoreError(f"pinecone_index_open_failed: {exc}") from exc
        return self._index

    def ensure_index(self) -> bool:
        """Create the serverless index if absent. Returns True when created."""
        from pinecone import ServerlessSpec

        client = self._get_client()
        try:
            if client.has_index(self._index_name):
                return False
            client.create_index(
                name=self._index_name,
                dimension=self._dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=self._cloud, region=self._region),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
            raise VectorStoreError(f"pinecone_create_index_failed: {exc}") from exc
        logger.info(
            "pinecone_index_created",
            extra={"indexName": self._index_name, "dimension": self._dimension},
        )
        return True

    # -- reads -----------------------------------------------------------

    def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[str, float]]:
        if not vector or limit <= 0:
            return []
        try:
            response = self._get_index().query(
                vector=list(vector),
                top_k=limit,
                namespace=self._namespace,
                filter=metadata_filter,
                include_values=False,
                include_metadata=False,
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
            raise VectorStoreError(f"pinecone_query_failed: {exc}") from exc
        return [(match.id, float(match.score)) for match in (response.matches or [])]

    def fetch(self, ids: Sequence[str]) -> dict[str, tuple[float, ...]]:
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return {}
        vectors: dict[str, tuple[float, ...]] = {}
        index = self._get_index()
        for start in range(0, len(unique_ids), _FETCH_BATCH_SIZE):
            batch = unique_ids[start : start + _FETCH_BATCH_SIZE]
            try:
                response = index.fetch(
                    ids=batch,
                    namespace=self._namespace,
                    timeout=self._timeout,
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
                raise VectorStoreError(f"pinecone_fetch_failed: {exc}") from exc
            for vector_id, record in (response.vectors or {}).items():
                if record.values:
                    vectors[vector_id] = tuple(float(value) for value in record.values)
        return vectors

    def list_ids(self) -> Iterator[str]:
        """Every id in the namespace, paginated. Used to prune stale chunks."""
        index = self._get_index()
        try:
            for page in index.list(namespace=self._namespace, timeout=self._timeout):
                for item in page.vectors or []:
                    if item.id:
                        yield item.id
        except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
            raise VectorStoreError(f"pinecone_list_failed: {exc}") from exc

    def count(self) -> int:
        try:
            stats = self._get_index().describe_index_stats(timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
            raise VectorStoreError(f"pinecone_stats_failed: {exc}") from exc
        namespaces = getattr(stats, "namespaces", None) or {}
        entry = namespaces.get(self._namespace)
        if entry is not None:
            return int(getattr(entry, "vector_count", 0) or 0)
        # A configured namespace that Pinecone does not report simply holds
        # nothing. Falling back to the index-wide total here would report
        # OTHER namespaces' vectors as this one's -- worst exactly when
        # you're chasing a namespace typo. The total is only the right
        # answer when no namespace was configured at all.
        return int(getattr(stats, "total_vector_count", 0) or 0) if not self._namespace else 0

    # -- writes ----------------------------------------------------------

    def upsert(self, records: Iterable[VectorRecord]) -> int:
        batch: list[dict[str, Any]] = []
        sent = 0
        for record in records:
            batch.append(
                {
                    "id": record.id,
                    "values": list(record.vector),
                    "metadata": record.metadata,
                }
            )
            if len(batch) >= _UPSERT_BATCH_SIZE:
                sent += self._flush(batch)
                batch = []
        if batch:
            sent += self._flush(batch)
        return sent

    def _flush(self, batch: list[dict[str, Any]]) -> int:
        try:
            self._get_index().upsert(
                vectors=batch,
                namespace=self._namespace,
                show_progress=False,
                # Bound the whole batch, not a single record.
                timeout=max(self._timeout, 60.0),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
            raise VectorStoreError(f"pinecone_upsert_failed: {exc}") from exc
        return len(batch)

    def delete(self, ids: Sequence[str]) -> None:
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return
        index = self._get_index()
        for start in range(0, len(unique_ids), _UPSERT_BATCH_SIZE):
            batch = unique_ids[start : start + _UPSERT_BATCH_SIZE]
            try:
                index.delete(ids=batch, namespace=self._namespace, timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 - surfaced as VectorStoreError
                raise VectorStoreError(f"pinecone_delete_failed: {exc}") from exc


@lru_cache(maxsize=4)
def _cached_store(
    api_key: str,
    index_name: str,
    namespace: str,
    timeout_seconds: float,
    dimension: int,
    cloud: str,
    region: str,
) -> PineconeVectorStore:
    return PineconeVectorStore(
        api_key=api_key,
        index_name=index_name,
        namespace=namespace,
        timeout_seconds=timeout_seconds,
        dimension=dimension,
        cloud=cloud,
        region=region,
    )


def get_vector_store(*, settings: Settings | None = None) -> PineconeVectorStore | None:
    """Cached store for the configured index, or None when Pinecone is unconfigured."""
    cfg = settings or get_settings()
    if not cfg.pinecone_available():
        return None
    return _cached_store(
        cfg.resolved_pinecone_api_key(),
        cfg.resolved_pinecone_index_name(),
        cfg.resolved_pinecone_namespace(),
        float(cfg.pinecone_timeout_seconds),
        int(cfg.pinecone_dimension),
        cfg.pinecone_cloud,
        cfg.pinecone_region,
    )


def reset_vector_store_cache() -> None:
    _cached_store.cache_clear()


__all__ = [
    "PineconeVectorStore",
    "VectorRecord",
    "VectorStore",
    "VectorStoreError",
    "get_vector_store",
    "reset_vector_store_cache",
]
