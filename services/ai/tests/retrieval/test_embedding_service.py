"""Tests for LLMod / OpenAI-compatible embedding configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.retrieval.embedding_service import (
    build_semantic_score_map,
    cosine_similarity,
    embed_query,
    reset_embeddings_client_cache,
)
from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page
from app.retrieval.profiles import get_profile
from app.retrieval.reranker import rerank_chunks


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
    # for the second (separately-constructed) OpenAIEmbeddings client this
    # module builds.
    from app.retrieval.embedding_service import _EMBEDDING_TIMEOUT_SECONDS, embed_query_cached

    embed_query_cached("hello", "test-key", "https://example.com/v1", "test-model")

    _, kwargs = mock_cls.call_args
    assert kwargs["timeout"] == _EMBEDDING_TIMEOUT_SECONDS


@patch("app.retrieval.embedding_service.get_embeddings_client")
def test_build_semantic_score_map(mock_get_client, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    client = MagicMock()
    client.embed_documents.return_value = [
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    mock_get_client.return_value = client

    scores = build_semantic_score_map(
        query="requirements",
        document_texts=["requirements text", "unrelated text"],
    )
    assert scores is not None
    assert scores[0] == pytest.approx(1.0)
    assert scores[1] == pytest.approx(0.0)


@patch("app.retrieval.embedding_service.build_semantic_score_map")
@patch("app.config.get_settings")
def test_rerank_uses_embedding_scores_when_available(mock_get_settings, mock_score_map, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    mock_get_settings.return_value = get_settings()
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    # index 0 = "Overview", index 1 = "Requirements" (see chunk_wiki_page's
    # ordering below). Both the keyword match (query "requirements" hits the
    # "Requirements" section title directly) and the mocked semantic score
    # favor "Requirements" here -- deliberately not an adversarial mock: with
    # both signals bounded to comparable scales (see
    # `reranker._normalize_bm25`), no legitimate weighting could rank a
    # chunk higher on keywords *and* lower on semantics than its competitor
    # and still lose, so a mock requiring exactly that outcome would be
    # testing for a bug, not a feature.
    mock_score_map.return_value = {0: 0.2, 1: 0.9}
    profile = get_profile("requirement_explanation")

    ranked = rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=profile,
    )

    assert ranked
    mock_score_map.assert_called_once()
    assert ranked[0][0].section_title == "Requirements"


@patch("app.retrieval.embedding_service.build_semantic_score_map", return_value=None)
@patch("app.config.get_settings")
def test_rerank_falls_back_without_embeddings(mock_get_settings, _mock_score_map, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    mock_get_settings.return_value = get_settings()
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    profile = get_profile("requirement_explanation")

    ranked = rerank_chunks(
        chunks,
        query="requirements",
        limit=2,
        profile=profile,
    )

    assert ranked
