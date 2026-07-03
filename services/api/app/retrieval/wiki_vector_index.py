"""In-memory wiki vector index with optional disk cache (LLMod embeddings)."""

from __future__ import annotations

import gzip
import hashlib
import heapq
import json
import logging
import math
import os
import pickle
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.retrieval.wiki_paths import resolve_wiki_root
from app.retrieval.embedding_service import embed_documents, embed_query_cached
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks
from app.retrieval.reranker import embedding_text

logger = logging.getLogger(__name__)
_CACHE_VERSION = 2
_MIN_PERSISTED_INDEX_ENTRIES = 500
_MIN_BACKUP_BYTES = 1024 * 1024
_BACKUP_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


def canonical_wiki_root(wiki_root: str) -> str:
    """Normalize wiki root so cache keys stay stable across relative/absolute paths."""
    return resolve_wiki_root(wiki_root)


def resolve_cache_path(path_or_settings: str | Path | Settings | None = None) -> Path:
    """Resolve the primary embedding index cache path to an absolute Path."""
    if isinstance(path_or_settings, Settings):
        configured = path_or_settings.resolved_embedding_index_cache_path()
    elif path_or_settings is None:
        configured = get_settings().resolved_embedding_index_cache_path()
    else:
        configured = str(path_or_settings)
    cache_path = Path(configured)
    if not cache_path.is_absolute():
        cache_path = (Path.cwd() / cache_path).resolve()
    return cache_path


def _wiki_roots_match(stored: str, requested: str) -> bool:
    if stored == requested:
        return True
    try:
        return canonical_wiki_root(stored) == canonical_wiki_root(requested)
    except (OSError, ValueError):
        return False


def _compact_cache_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.compact.pkl.gz")


def _meta_cache_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.meta.json")


def _backup_directory(cache_path: Path) -> Path:
    return cache_path.parent / "backups"


def _backup_latest_path(cache_path: Path) -> Path:
    return _backup_directory(cache_path) / f"{cache_path.stem}.compact.latest.pkl.gz"


def _list_timestamped_backups(cache_path: Path) -> list[Path]:
    backup_dir = _backup_directory(cache_path)
    if not backup_dir.is_dir():
        return []
    pattern = f"{cache_path.stem}.compact.*.pkl.gz"
    backups = [
        path
        for path in backup_dir.glob(pattern)
        if path.name != _backup_latest_path(cache_path).name
    ]
    backups.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return backups


def _iter_cache_file_candidates(cache_path: Path) -> list[Path]:
    candidates: list[Path] = []
    compact_path = _compact_cache_path(cache_path)
    if compact_path.is_file():
        candidates.append(compact_path)
    latest_backup = _backup_latest_path(cache_path)
    if latest_backup.is_file() and latest_backup not in candidates:
        candidates.append(latest_backup)
    for backup in _list_timestamped_backups(cache_path):
        if backup not in candidates:
            candidates.append(backup)
    return candidates


def _prune_backups(cache_path: Path, *, max_count: int) -> None:
    if max_count <= 0:
        return
    backups = _list_timestamped_backups(cache_path)
    for stale in backups[max_count:]:
        try:
            stale.unlink()
        except OSError:
            logger.exception("wiki_vector_index_backup_prune_failed", extra={"path": str(stale)})


def _backup_compact_cache(
    cache_path: Path,
    compact_path: Path,
    *,
    max_backups: int,
) -> Path | None:
    if not compact_path.is_file():
        return None
    size_bytes = compact_path.stat().st_size
    if size_bytes < _MIN_BACKUP_BYTES:
        return None

    backup_dir = _backup_directory(cache_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime(_BACKUP_TIMESTAMP_FORMAT)
    stamped = backup_dir / f"{cache_path.stem}.compact.{timestamp}.pkl.gz"
    latest = _backup_latest_path(cache_path)
    shutil.copy2(compact_path, stamped)
    shutil.copy2(compact_path, latest)
    _prune_backups(cache_path, max_count=max_backups)
    logger.info(
        "wiki_vector_index_backup_created",
        extra={
            "backupPath": str(stamped),
            "latestPath": str(latest),
            "sizeBytes": size_bytes,
        },
    )
    return stamped


def _write_cache_metadata(
    cache_path: Path,
    *,
    index: WikiVectorIndex,
    compact_path: Path,
    backup_path: str | None = None,
) -> None:
    meta_path = _meta_cache_path(cache_path)
    payload = {
        "version": _CACHE_VERSION,
        "wikiRoot": canonical_wiki_root(index.wiki_root),
        "model": index.model,
        "entryCount": len(index.entries),
        "savedAt": datetime.now(UTC).isoformat(),
        "compactPath": str(compact_path),
        "compactSizeBytes": compact_path.stat().st_size if compact_path.is_file() else 0,
        "backupPath": backup_path,
    }
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _atomic_write_compact(compact_path: Path, payload: dict[str, Any]) -> None:
    compact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = compact_path.with_name(f"{compact_path.name}.tmp-{os.getpid()}")
    try:
        with gzip.open(temp_path, "wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        temp_path.replace(compact_path)
    finally:
        if temp_path.is_file():
            try:
                temp_path.unlink()
            except OSError:
                logger.exception("wiki_vector_index_temp_cleanup_failed", extra={"path": str(temp_path)})


def _remove_corrupt_cache_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        logger.exception("wiki_vector_index_compact_cache_cleanup_failed", extra={"path": str(path)})


def chunk_cache_key(chunk: WikiChunk) -> str:
    digest = hashlib.sha256(
        f"{chunk.source_file}|{chunk.section_title}|{chunk.content}".encode("utf-8")
    ).hexdigest()
    return f"{chunk.source_file}::{chunk.section_title}::{digest[:16]}"


def _normalize_vector(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return tuple(value / norm for value in vector)


def _format_disk_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= 10:
        return f"{size_mb:.0f} MB"
    if size_mb >= 1:
        return f"{size_mb:.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


@dataclass(frozen=True)
class IndexedWikiChunk:
    key: str
    chunk: WikiChunk
    vector: tuple[float, ...]


@dataclass
class WikiVectorIndex:
    model: str
    wiki_root: str
    entries: list[IndexedWikiChunk]
    _vector_by_key: dict[str, tuple[float, ...]] = field(repr=False)
    _normalized_by_key: dict[str, tuple[float, ...]] = field(repr=False)
    _chunk_by_key: dict[str, WikiChunk] = field(repr=False)

    @classmethod
    def from_entries(
        cls,
        *,
        model: str,
        wiki_root: str,
        entries: list[IndexedWikiChunk],
    ) -> WikiVectorIndex:
        vector_by_key = {entry.key: entry.vector for entry in entries}
        normalized_by_key = {
            key: _normalize_vector(vector) for key, vector in vector_by_key.items()
        }
        chunk_by_key = {entry.key: entry.chunk for entry in entries}
        return cls(
            model=model,
            wiki_root=wiki_root,
            entries=entries,
            _vector_by_key=vector_by_key,
            _normalized_by_key=normalized_by_key,
            _chunk_by_key=chunk_by_key,
        )

    def semantic_scores(
        self,
        query_vector: list[float],
        *,
        limit: int,
    ) -> list[tuple[WikiChunk, float]]:
        if not query_vector or limit <= 0:
            return []
        query_norm = _normalize_vector(tuple(query_vector))
        if not query_norm:
            return []

        scored: list[tuple[float, WikiChunk]] = []
        for key, normalized in self._normalized_by_key.items():
            score = sum(left * right for left, right in zip(query_norm, normalized, strict=True))
            if score > 0.0:
                scored.append((score, self._chunk_by_key[key]))

        if len(scored) <= limit:
            scored.sort(key=lambda item: item[0], reverse=True)
            return [(chunk, score) for score, chunk in scored]

        best = heapq.nlargest(limit, scored, key=lambda item: item[0])
        return [(chunk, score) for score, chunk in best]

    def vector_for_chunk(self, chunk: WikiChunk) -> list[float] | None:
        vector = self._vector_by_key.get(chunk_cache_key(chunk))
        return list(vector) if vector else None


def format_index_cache_loaded_message(
    index: WikiVectorIndex,
    cache_path: Path,
) -> str:
    """Human-readable summary when a persisted wiki index is loaded from disk."""
    compact_path = _compact_cache_path(cache_path)
    if compact_path.is_file():
        size_bytes = compact_path.stat().st_size
    elif cache_path.is_file():
        size_bytes = cache_path.stat().st_size
    else:
        size_bytes = 0
    return (
        f"Loaded wiki index from disk ({len(index.entries):,} chunks, "
        f"{_format_disk_size(size_bytes)})"
    )


def _log_disk_cache_hit(index: WikiVectorIndex, cache_path: Path) -> None:
    logger.info(format_index_cache_loaded_message(index, cache_path))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_index_build_cost(*, wiki_root: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    chunks = list(load_wiki_chunks(wiki_root))
    texts = [embedding_text(chunk) for chunk in chunks]
    total_tokens = sum(_estimate_tokens(text) for text in texts)
    batch_size = max(1, int(cfg.embedding_index_batch_size or 64))
    return {
        "wikiRoot": wiki_root,
        "chunkCount": len(chunks),
        "estimatedInputTokens": total_tokens,
        "embeddingModel": cfg.resolved_embedding_model(),
        "batchCount": (len(texts) + batch_size - 1) // batch_size if texts else 0,
        "notes": "One-time index build. Rebuild only when wiki content or model changes.",
    }


def estimate_query_embedding_cost(*, query_count: int, avg_query_tokens: int = 12) -> dict[str, Any]:
    return {
        "queryCount": query_count,
        "estimatedInputTokens": query_count * avg_query_tokens,
        "notes": "Per-query cost when index cache is warm (query embedding only).",
    }


def _entries_from_keys_and_vectors(
    *,
    wiki_root: str,
    keys: list[str],
    vectors: list[tuple[float, ...] | list[float]],
) -> list[IndexedWikiChunk]:
    chunks = load_wiki_chunks(wiki_root)
    chunk_by_key = {chunk_cache_key(chunk): chunk for chunk in chunks}
    entries: list[IndexedWikiChunk] = []
    for key, vector in zip(keys, vectors, strict=True):
        chunk = chunk_by_key.get(key)
        if chunk is None:
            continue
        entries.append(
            IndexedWikiChunk(
                key=key,
                chunk=chunk,
                vector=tuple(float(value) for value in vector),
            )
        )
    return entries


def _load_compact_cache(
    path: Path,
    *,
    wiki_root: str,
    model: str,
    delete_on_corrupt: bool = False,
) -> WikiVectorIndex | None:
    canonical_root = canonical_wiki_root(wiki_root)
    try:
        with gzip.open(path, "rb") as handle:
            payload = pickle.load(handle)
    except (EOFError, OSError, pickle.PickleError):
        logger.warning("wiki_vector_index_compact_cache_corrupt", extra={"path": str(path)})
        if delete_on_corrupt:
            _remove_corrupt_cache_file(path)
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("version") or 0) != _CACHE_VERSION:
        return None
    stored_root = str(payload.get("wikiRoot") or "")
    if not _wiki_roots_match(stored_root, canonical_root):
        return None
    if str(payload.get("model") or "") != model:
        return None
    keys = payload.get("keys")
    vectors = payload.get("vectors")
    if not isinstance(keys, list) or not isinstance(vectors, list):
        return None
    entries = _entries_from_keys_and_vectors(
        wiki_root=canonical_root,
        keys=[str(key) for key in keys],
        vectors=vectors,
    )
    if not entries:
        return None
    return WikiVectorIndex.from_entries(
        model=model,
        wiki_root=canonical_root,
        entries=entries,
    )


def _restore_primary_from_backup(cache_path: Path, *, source: Path) -> None:
    compact_path = _compact_cache_path(cache_path)
    shutil.copy2(source, compact_path)
    logger.info(
        "wiki_vector_index_primary_restored_from_backup",
        extra={"source": str(source), "target": str(compact_path)},
    )


def _load_legacy_json_cache(path: Path, *, wiki_root: str, model: str) -> WikiVectorIndex | None:
    canonical_root = canonical_wiki_root(wiki_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not _wiki_roots_match(str(payload.get("wikiRoot") or ""), canonical_root):
        return None
    if str(payload.get("model") or "") != model:
        return None

    entries: list[IndexedWikiChunk] = []
    for item in payload.get("entries") or []:
        if not isinstance(item, dict):
            continue
        chunk_payload = item.get("chunk")
        vector = item.get("vector")
        if not isinstance(chunk_payload, dict) or not isinstance(vector, list):
            continue
        chunk = WikiChunk(
            source_file=str(chunk_payload.get("source_file") or ""),
            page_title=str(chunk_payload.get("page_title") or ""),
            section_title=str(chunk_payload.get("section_title") or ""),
            heading_path=tuple(chunk_payload.get("heading_path") or ()),
            content=str(chunk_payload.get("content") or ""),
            catalog_year=chunk_payload.get("catalog_year"),
            faculty=chunk_payload.get("faculty"),
            degree_program=chunk_payload.get("degree_program"),
            track=chunk_payload.get("track"),
            course_numbers_mentioned=tuple(chunk_payload.get("course_numbers_mentioned") or ()),
            language=str(chunk_payload.get("language") or "he"),
        )
        entries.append(
            IndexedWikiChunk(
                key=str(item.get("key") or chunk_cache_key(chunk)),
                chunk=chunk,
                vector=tuple(float(value) for value in vector),
            )
        )
    if not entries:
        return None
    return WikiVectorIndex.from_entries(model=model, wiki_root=canonical_root, entries=entries)


def load_index_from_cache(path: Path, *, wiki_root: str, model: str) -> WikiVectorIndex | None:
    canonical_root = canonical_wiki_root(wiki_root)
    compact_path = _compact_cache_path(path)
    for candidate in _iter_cache_file_candidates(path):
        loaded = _load_compact_cache(
            candidate,
            wiki_root=canonical_root,
            model=model,
            delete_on_corrupt=candidate == compact_path,
        )
        if loaded is None:
            continue
        if candidate != compact_path:
            logger.warning(
                "wiki_vector_index_loaded_from_backup",
                extra={"backupPath": str(candidate), "cachePath": str(compact_path)},
            )
            try:
                _restore_primary_from_backup(path, source=candidate)
            except OSError:
                logger.exception("wiki_vector_index_primary_restore_failed")
        return loaded

    if not path.is_file():
        return None

    legacy = _load_legacy_json_cache(path, wiki_root=canonical_root, model=model)
    if legacy is None:
        return None

    try:
        save_index_to_cache(path, legacy)
    except OSError:
        logger.exception("wiki_vector_index_compact_migration_failed")
    return legacy


def save_index_to_cache(
    path: Path,
    index: WikiVectorIndex,
    *,
    allow_small: bool = False,
    settings: Settings | None = None,
) -> None:
    if not allow_small and len(index.entries) < _MIN_PERSISTED_INDEX_ENTRIES:
        logger.warning(
            "wiki_vector_index_cache_skip_small_index",
            extra={
                "entryCount": len(index.entries),
                "wikiRoot": index.wiki_root,
                "cachePath": str(path),
            },
        )
        return

    cfg = settings or get_settings()
    canonical_root = canonical_wiki_root(index.wiki_root)
    normalized_index = (
        WikiVectorIndex.from_entries(
            model=index.model,
            wiki_root=canonical_root,
            entries=index.entries,
        )
        if index.wiki_root != canonical_root
        else index
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    compact_path = _compact_cache_path(path)
    backup_path = _backup_compact_cache(
        path,
        compact_path,
        max_backups=cfg.resolved_embedding_index_cache_backup_count(),
    )
    payload = {
        "version": _CACHE_VERSION,
        "wikiRoot": canonical_root,
        "model": normalized_index.model,
        "keys": [entry.key for entry in normalized_index.entries],
        "vectors": [entry.vector for entry in normalized_index.entries],
    }
    _atomic_write_compact(compact_path, payload)

    verified = _load_compact_cache(
        compact_path,
        wiki_root=canonical_root,
        model=normalized_index.model,
        delete_on_corrupt=True,
    )
    if verified is None or len(verified.entries) != len(normalized_index.entries):
        raise OSError(
            f"Wiki vector index cache verification failed for {compact_path}"
        )

    _write_cache_metadata(
        path,
        index=normalized_index,
        compact_path=compact_path,
        backup_path=str(backup_path) if backup_path is not None else None,
    )

    if path.is_file() and path.suffix == ".json":
        try:
            path.unlink()
        except OSError:
            logger.exception("wiki_vector_index_legacy_json_cleanup_failed")


def verify_index_cache(
    *,
    cache_path: Path | None = None,
    wiki_root: str,
    model: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Load cache from disk (including backups) and return verification metadata."""
    cfg = settings or get_settings()
    resolved_path = cache_path or resolve_cache_path(cfg)
    resolved_model = model or cfg.resolved_embedding_model()
    canonical_root = canonical_wiki_root(wiki_root)
    loaded = load_index_from_cache(
        resolved_path,
        wiki_root=canonical_root,
        model=resolved_model,
    )
    compact_path = _compact_cache_path(resolved_path)
    meta_path = _meta_cache_path(resolved_path)
    if loaded is not None and compact_path.is_file() and not meta_path.is_file():
        try:
            _write_cache_metadata(
                resolved_path,
                index=loaded,
                compact_path=compact_path,
            )
        except OSError:
            logger.exception("wiki_vector_index_meta_sync_failed")
    backups = _list_timestamped_backups(resolved_path)
    latest_backup = _backup_latest_path(resolved_path)
    return {
        "ok": loaded is not None,
        "cachePath": str(resolved_path),
        "compactPath": str(compact_path),
        "compactExists": compact_path.is_file(),
        "compactSizeBytes": compact_path.stat().st_size if compact_path.is_file() else 0,
        "metaPath": str(meta_path),
        "metaExists": meta_path.is_file(),
        "wikiRoot": canonical_root,
        "model": resolved_model,
        "entryCount": len(loaded.entries) if loaded is not None else 0,
        "backupCount": len(backups),
        "latestBackupPath": str(latest_backup) if latest_backup.is_file() else None,
        "latestBackupSizeBytes": latest_backup.stat().st_size if latest_backup.is_file() else 0,
    }


def backup_index_cache(
    *,
    cache_path: Path | None = None,
    settings: Settings | None = None,
) -> Path | None:
    """Create a timestamped backup of the current compact cache file."""
    cfg = settings or get_settings()
    resolved_path = cache_path or resolve_cache_path(cfg)
    compact_path = _compact_cache_path(resolved_path)
    return _backup_compact_cache(
        resolved_path,
        compact_path,
        max_backups=cfg.resolved_embedding_index_cache_backup_count(),
    )


def restore_index_cache_from_backup(
    *,
    cache_path: Path | None = None,
    source: Path | None = None,
    settings: Settings | None = None,
) -> Path | None:
    """Restore the primary compact cache from latest or a specific backup file."""
    cfg = settings or get_settings()
    resolved_path = cache_path or resolve_cache_path(cfg)
    compact_path = _compact_cache_path(resolved_path)
    backup_source = source
    if backup_source is None:
        latest = _backup_latest_path(resolved_path)
        backup_source = latest if latest.is_file() else None
    if backup_source is None or not backup_source.is_file():
        return None
    _restore_primary_from_backup(resolved_path, source=backup_source)
    return compact_path


def _store_runtime_index(index: WikiVectorIndex, *, settings: Settings) -> None:
    global _index_cache, _index_cache_key
    _index_cache = index
    _index_cache_key = (
        f"{canonical_wiki_root(index.wiki_root)}|{settings.resolved_embedding_model()}|"
        f"{settings.resolved_embedding_index_cache_path()}"
    )


def build_wiki_vector_index(
    *,
    wiki_root: str,
    settings: Settings | None = None,
    force_rebuild: bool = False,
    allow_build: bool = True,
    on_batch_embedded: Callable[[int, int], None] | None = None,
) -> WikiVectorIndex | None:
    cfg = settings or get_settings()
    if not cfg.wiki_vector_index_enabled():
        return None

    canonical_root = canonical_wiki_root(wiki_root)
    cache_path = resolve_cache_path(cfg)
    model = cfg.resolved_embedding_model()

    if not force_rebuild:
        cached = load_index_from_cache(cache_path, wiki_root=canonical_root, model=model)
        if cached is not None:
            _log_disk_cache_hit(cached, cache_path)
            _store_runtime_index(cached, settings=cfg)
            return cached

    if not allow_build:
        logger.warning(
            "wiki_vector_index_cache_miss_skip_build",
            extra={"wikiRoot": canonical_root, "cachePath": str(cache_path)},
        )
        return None

    chunks = list(load_wiki_chunks(canonical_root))
    if not chunks:
        return None

    texts = [embedding_text(chunk) for chunk in chunks]
    batch_size = max(1, int(cfg.embedding_index_batch_size or 64))
    total_batches = (len(texts) + batch_size - 1) // batch_size if texts else 0
    vectors: list[list[float]] = []
    for batch_index, start in enumerate(range(0, len(texts), batch_size), start=1):
        batch_vectors = embed_documents(texts[start : start + batch_size], settings=cfg)
        if not batch_vectors:
            logger.warning("wiki_vector_index_build_failed_batch", extra={"start": start})
            return None
        vectors.extend(batch_vectors)
        if on_batch_embedded is not None:
            on_batch_embedded(batch_index, total_batches)

    entries = [
        IndexedWikiChunk(
            key=chunk_cache_key(chunk),
            chunk=chunk,
            vector=tuple(vector),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    index = WikiVectorIndex.from_entries(
        model=model,
        wiki_root=canonical_root,
        entries=entries,
    )
    try:
        save_index_to_cache(cache_path, index, settings=cfg)
    except OSError:
        logger.exception("wiki_vector_index_cache_write_failed")
    _store_runtime_index(index, settings=cfg)
    return index


_index_cache: WikiVectorIndex | None = None
_index_cache_key: str | None = None


def get_wiki_vector_index(
    *,
    wiki_root: str,
    settings: Settings | None = None,
    allow_build: bool = True,
) -> WikiVectorIndex | None:
    global _index_cache, _index_cache_key
    cfg = settings or get_settings()
    if not cfg.wiki_vector_index_enabled():
        return None

    canonical_root = canonical_wiki_root(wiki_root)
    key = (
        f"{canonical_root}|{cfg.resolved_embedding_model()}|"
        f"{cfg.resolved_embedding_index_cache_path()}"
    )
    if _index_cache is not None and _index_cache_key == key:
        return _index_cache

    index = build_wiki_vector_index(
        wiki_root=canonical_root,
        settings=cfg,
        force_rebuild=False,
        allow_build=allow_build,
    )
    return index


def reset_wiki_vector_index_runtime_cache() -> None:
    global _index_cache, _index_cache_key
    _index_cache = None
    _index_cache_key = None


def query_semantic_candidates(
    *,
    query: str,
    wiki_root: str,
    limit: int,
    settings: Settings | None = None,
) -> list[tuple[WikiChunk, float]]:
    cfg = settings or get_settings()
    if not cfg.embeddings_available():
        return []
    index = get_wiki_vector_index(wiki_root=wiki_root, settings=cfg)
    if index is None:
        return []
    query_vector = embed_query_cached(
        query,
        cfg.resolved_embedding_api_key(),
        cfg.resolved_embedding_base_url(),
        cfg.resolved_embedding_model(),
    )
    if not query_vector:
        return []
    return index.semantic_scores(list(query_vector), limit=limit)
