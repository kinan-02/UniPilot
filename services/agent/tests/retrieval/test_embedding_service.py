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
    mock_score_map.return_value = {0: 0.95, 1: 0.1}
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
