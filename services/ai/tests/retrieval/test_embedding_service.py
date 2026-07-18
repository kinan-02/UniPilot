"""Tests for LLMod / OpenAI-compatible embedding configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.retrieval.embedding_service import (
    cosine_similarity,
    embed_query,
    reset_embeddings_client_cache,
)
from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page
from app.retrieval.profiles import get_profile
from app.retrieval.reranker import rerank_chunks
from app.retrieval.wiki_vector_index import chunk_vector_id


SAMPLE_PAGE = """---
title: Test Degree
track_slug: track-test
catalog_year: 2025
---

# Overview
General overview text for the DDS track requirements document.

## Requirements
Students must complete course 00940139 and electives.
"""


def setup_function() -> None:
    get_settings.cache_clear()
    reset_embeddings_client_cache()


def test_settings_resolve_embedding_defaults(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.resolved_embedding_base_url() == "https://api.llmod.ai/v1"
    assert settings.resolved_embedding_model() == "MB5R2CF-azure/text-embedding-3-small"
    assert settings.embeddings_available() is True


def test_settings_requires_dedicated_embedding_key():
    from app.config import Settings

    settings = Settings(
        _env_file=None,
        embedding_api_key=None,
        embedding_enabled=True,
        openai_api_key="shared-deepseek-key",
    )
    assert settings.resolved_embedding_api_key() == ""
    assert settings.embeddings_available() is False


def test_embeddings_disabled_when_flag_false(monkeypatch):
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.embeddings_available() is False
    assert embed_query("hello", settings=settings) is None


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


@patch("langchain_openai.OpenAIEmbeddings")
def test_get_embeddings_client_sets_an_explicit_timeout(mock_cls, monkeypatch):
    # Regression guard: `OpenAIEmbeddings` defaults `timeout` to `None`
    # (unbounded). A live-eval run found this causing a turn's own
    # asyncio.wait_for(300s) to elapse at 463s instead once embeddings were
    # configured -- a stalled embeddings call has no timeout of its own to
    # bound it.
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.retrieval.embedding_service import _EMBEDDING_TIMEOUT_SECONDS, get_embeddings_client

    get_embeddings_client()

    _, kwargs = mock_cls.call_args
    assert kwargs["timeout"] == _EMBEDDING_TIMEOUT_SECONDS


@patch("langchain_openai.OpenAIEmbeddings")
def test_embed_query_cached_sets_an_explicit_timeout(mock_cls):
    # Same regression guard as the `get_embeddings_client` version above,
    # reached via the query path rather than the document path.
    from app.retrieval.embedding_service import _EMBEDDING_TIMEOUT_SECONDS, embed_query_cached

    embed_query_cached("hello", "test-key", "https://example.com/v1", "test-model")

    _, kwargs = mock_cls.call_args
    assert kwargs["timeout"] == _EMBEDDING_TIMEOUT_SECONDS


@patch("langchain_openai.OpenAIEmbeddings")
def test_query_and_document_paths_share_one_pooled_client(mock_cls, monkeypatch):
    """Rebuilding a client per call costs a fresh TLS handshake every time.

    Measured against api.llmod.ai: 798ms per uncached query with a new client
    vs 466ms reusing one. Both entry points must land on the same instance.
    """
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
    get_settings.cache_clear()
    from app.retrieval.embedding_service import embed_query_cached, get_embeddings_client

    get_embeddings_client()
    embed_query_cached("first", "test-key", "https://example.com/v1", "test-model")
    embed_query_cached("second", "test-key", "https://example.com/v1", "test-model")

    # Two distinct queries plus the document client -- still one construction.
    assert mock_cls.call_count == 1


def _enable_semantic_search(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-pinecone-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    get_settings.cache_clear()


def test_rerank_uses_embedding_scores_when_available(monkeypatch):
    _enable_semantic_search(monkeypatch)
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    # index 0 = "Overview", index 1 = "Requirements" (see chunk_wiki_page's
    # ordering below). Both the keyword match (query "requirements" hits the
    # "Requirements" section title directly) and the stubbed vectors favor
    # "Requirements" here -- deliberately not an adversarial mock: with both
    # signals bounded to comparable scales (see `reranker._normalize_bm25`),
    # no legitimate weighting could rank a chunk higher on keywords *and*
    # lower on semantics than its competitor and still lose, so a mock
    # requiring exactly that outcome would be testing for a bug, not a
    # feature.
    query_vector = (1.0, 0.0)
    vectors_by_id = {
        chunk_vector_id(chunks[0]): (0.2, 0.98),  # Overview: near-orthogonal
        chunk_vector_id(chunks[1]): (1.0, 0.0),  # Requirements: aligned
    }
    fetch_calls: list[int] = []

    def _fake_fetch(candidate_chunks, **_kwargs):
        fetch_calls.append(len(list(candidate_chunks)))
        return vectors_by_id

    monkeypatch.setattr("app.retrieval.wiki_vector_index.fetch_chunk_vectors", _fake_fetch)
    monkeypatch.setattr(
        "app.retrieval.embedding_service.embed_query_cached",
        lambda *_args, **_kwargs: query_vector,
    )
    profile = get_profile("requirement_explanation")

    ranked = rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=profile,
    )

    assert ranked
    # One batched fetch for the whole candidate set, not one call per chunk.
    assert fetch_calls == [len(chunks)]
    assert ranked[0][0].section_title == "Requirements"


def test_rerank_page_scoped_uses_the_filtered_query_not_a_fetch(monkeypatch):
    """One scoped query returning scores, instead of fetching every vector."""
    _enable_semantic_search(monkeypatch)
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    scoped_calls: list[int] = []

    def _fake_scoped(candidate_chunks, **_kwargs):
        candidates = list(candidate_chunks)
        scoped_calls.append(len(candidates))
        # favour "Requirements" (index 1), same rationale as the test above
        return {chunk_vector_id(c): (0.2, 0.9)[i] for i, c in enumerate(candidates)}

    def _explode(*_args, **_kwargs):
        raise AssertionError("page_scoped must not fall back to fetch_chunk_vectors")

    monkeypatch.setattr("app.retrieval.wiki_vector_index.score_page_scoped_chunks", _fake_scoped)
    monkeypatch.setattr("app.retrieval.wiki_vector_index.fetch_chunk_vectors", _explode)

    ranked = rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=get_profile("requirement_explanation"),
        page_scoped=True,
    )

    assert scoped_calls == [len(chunks)]
    assert ranked[0][0].section_title == "Requirements"


def test_rerank_defaults_to_fetch_for_arbitrary_candidate_sets(monkeypatch):
    """Only page-scoped callers may use the filtered query — see its contract."""
    _enable_semantic_search(monkeypatch)
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)

    def _explode(*_args, **_kwargs):
        raise AssertionError("must not use the page-scoped query by default")

    monkeypatch.setattr("app.retrieval.wiki_vector_index.score_page_scoped_chunks", _explode)
    monkeypatch.setattr(
        "app.retrieval.wiki_vector_index.fetch_chunk_vectors",
        lambda candidate_chunks, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.retrieval.embedding_service.embed_query_cached",
        lambda *_args, **_kwargs: (1.0, 0.0),
    )

    assert rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=get_profile("requirement_explanation"),
    )


def test_rerank_reuses_supplied_scores_and_fetches_only_the_remainder(monkeypatch):
    """`search_wiki` already holds Pinecone's cosine for its semantic half.

    Re-fetching those vectors to recompute the identical number was the
    single biggest cost in the pipeline (2105ms for 114 ids).
    """
    from app.retrieval.wiki_vector_index import chunk_vector_id

    _enable_semantic_search(monkeypatch)
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    already_known = {chunk_vector_id(chunks[0]): 0.8}
    fetched: list[int] = []

    def _fake_fetch(candidate_chunks, **_kwargs):
        candidates = list(candidate_chunks)
        fetched.append(len(candidates))
        # Whatever is fetched must be the chunks WITHOUT a supplied score.
        assert all(chunk_vector_id(c) not in already_known for c in candidates)
        return {}

    monkeypatch.setattr("app.retrieval.wiki_vector_index.fetch_chunk_vectors", _fake_fetch)
    monkeypatch.setattr(
        "app.retrieval.embedding_service.embed_query_cached",
        lambda *_args, **_kwargs: (1.0, 0.0),
    )

    rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=get_profile("requirement_explanation"),
        semantic_scores=already_known,
    )

    assert fetched == [len(chunks) - 1]


def test_rerank_skips_the_fetch_entirely_when_all_scores_are_supplied(monkeypatch):
    from app.retrieval.wiki_vector_index import chunk_vector_id

    _enable_semantic_search(monkeypatch)
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)

    def _explode(*_args, **_kwargs):
        raise AssertionError("no fetch is needed when every score was supplied")

    monkeypatch.setattr("app.retrieval.wiki_vector_index.fetch_chunk_vectors", _explode)

    assert rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=get_profile("requirement_explanation"),
        semantic_scores={chunk_vector_id(c): 0.5 for c in chunks},
    )


def test_missing_semantic_score_contributes_zero_not_lexical_overlap():
    """A ranking must not mix cosine with a keyword-derived stand-in.

    Measured over 114 real candidates, the retired lexical fallback ran
    0.200-0.900 against a true cosine range of 0.257-0.747 and did not
    correlate -- higher for 29% of chunks, lower for the rest.
    """
    from app.retrieval.reranker import semantic_similarity_score

    assert semantic_similarity_score(semantic_override=None) == 0.0
    assert semantic_similarity_score(semantic_override=0.62) == pytest.approx(0.62)
    assert semantic_similarity_score(semantic_override=-0.3) == 0.0


def test_rerank_respects_limit_even_when_more_candidates_score(monkeypatch):
    _enable_semantic_search(monkeypatch)
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    assert len(rerank_chunks(chunks, query="requirements", limit=1)) == 1


def test_rerank_falls_back_to_keywords_without_pinecone(monkeypatch):
    """Pinecone unconfigured must still rank, on BM25 alone."""
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_API_KEY", "")
    get_settings.cache_clear()
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    profile = get_profile("requirement_explanation")

    def _explode(*_args, **_kwargs):
        raise AssertionError("must not reach Pinecone when it is unconfigured")

    monkeypatch.setattr("app.retrieval.wiki_vector_index.fetch_chunk_vectors", _explode)

    ranked = rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=profile,
    )

    assert ranked
