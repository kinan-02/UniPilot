"""Resolve paths and pre-warm retrieval caches for eval runs."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.retrieval.graph_retriever import warmup_graph_engine
from app.retrieval.profiles import load_profile_config
from app.retrieval.wiki_paths import resolve_wiki_root


def warmup_retrieval_caches(
    *,
    wiki_root: str | None = None,
    settings: Settings | None = None,
    load_vector_index: bool = True,
    allow_index_build: bool = True,
) -> str:
    """Load profiles and the academic graph engine before a benchmark loop.

    ``load_vector_index`` and ``allow_index_build`` are accepted for backward
    compatibility with legacy RAG eval scripts but are ignored — the live path
    uses the wiki graph + semester JSON engine instead of embedding indexes.
    """
    _ = (load_vector_index, allow_index_build)
    cfg = settings or get_settings()
    configured = (wiki_root or cfg.academic_wiki_path or "").strip()
    if not configured:
        return ""
    resolved = resolve_wiki_root(configured)
    load_profile_config()
    warmup_graph_engine(settings=cfg)
    return resolved
