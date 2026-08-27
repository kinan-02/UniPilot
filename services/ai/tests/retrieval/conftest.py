"""Retrieval test isolation — keep pytest off the network."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.embedding_service import reset_embeddings_client_cache
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.wiki_vector_index import reset_wiki_vector_index_runtime_cache


@pytest.fixture(autouse=True)
def isolate_retrieval_vector_store(monkeypatch):
    """Force Pinecone to read as unconfigured for every retrieval test.

    Set to empty rather than deleted on purpose: `Settings` also reads the
    repo-root `.env`, and `delenv` would not mask a real key living there.
    An explicit empty env var takes precedence over the file, so a developer
    with working credentials still gets offline, deterministic tests.
    """
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
    # Embedding clients are pooled by credential set, so a client cached by an
    # earlier test would otherwise outlive its patched `OpenAIEmbeddings`.
    reset_embeddings_client_cache()
    yield
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_wiki_vector_index_runtime_cache()
    # Deliberately NOT resetting the embedding caches on teardown: this
    # fixture unwinds before `monkeypatch` undoes its own patches, so a test
    # that replaced `embed_query_cached` with a plain stub would still have
    # that stub installed here -- and stubs have no `.cache_clear()`. The
    # setup call above is what actually provides isolation.
