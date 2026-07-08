"""Retrieval test isolation — keep pytest from overwriting dev embedding caches."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.wiki_vector_index import reset_wiki_vector_index_runtime_cache


@pytest.fixture(autouse=True)
def isolate_retrieval_embedding_cache(tmp_path, monkeypatch):
    """Route wiki vector index cache to a per-test temp file."""
    monkeypatch.setenv(
        "EMBEDDING_INDEX_CACHE_PATH",
        str(tmp_path / "wiki_embedding_index.json"),
    )
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
    yield
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
