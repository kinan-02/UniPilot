"""Resolve wiki paths and pre-warm retrieval caches for eval runs."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.retrieval.obsidian_wiki_indexer import load_wiki_chunks
from app.retrieval.profiles import load_profile_config
from app.retrieval.wiki_paths import resolve_wiki_root
from app.retrieval.wiki_vector_index import get_wiki_vector_index


def warmup_retrieval_caches(
    *,
    wiki_root: str | None = None,
    settings: Settings | None = None,
    load_vector_index: bool = True,
    allow_index_build: bool = True,
) -> str:
    """Load wiki chunks, profiles, and vector index once before a benchmark loop."""
    cfg = settings or get_settings()
    configured = (wiki_root or cfg.catalog_vault_wiki_path or "").strip()
    if not configured:
        return ""
    resolved = resolve_wiki_root(configured)
    load_profile_config()
    load_wiki_chunks(resolved)
    if load_vector_index and cfg.wiki_vector_index_enabled() and cfg.embeddings_available():
        get_wiki_vector_index(
            wiki_root=resolved,
            settings=cfg,
            allow_build=allow_index_build,
        )
    return resolved
