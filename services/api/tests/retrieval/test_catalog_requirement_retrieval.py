"""Regression tests for requirement/catalog wiki retrieval."""

from __future__ import annotations

import pytest

from app.retrieval.hybrid_wiki_retriever import retrieve_wiki_context_with_profile
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.profiles import get_profile, reset_profile_config_cache


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    track_dir = wiki / "entities" / "tracks"
    track_dir.mkdir(parents=True)
    (track_dir / "track-test.md").write_text(
        """---
title: Track Test Degree
track_slug: track-test
catalog_year: 2025
---

# Requirements
Students must complete mandatory core courses.

## Elective bucket
Choose electives from approved pool.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(wiki))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()
    yield
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()


@pytest.mark.asyncio
async def test_requirement_bucket_retrieval(wiki_dir):
    profile = get_profile("catalog_requirement_lookup")
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="degree requirements elective bucket",
        user_context={"profile": {"track": "track-test", "catalogYear": 2025}},
        entities={},
        profile=profile,
    )
    assert snippets
    assert metadata["profileName"] == "catalog_requirement_lookup"


@pytest.mark.asyncio
async def test_hebrew_requirement_query(wiki_dir):
    profile = get_profile("requirement_explanation")
    snippets, _records, _meta = await retrieve_wiki_context_with_profile(
        query="דרישות בחירה במסלול",
        user_context={"profile": {"track": "track-test", "catalogYear": 2025}},
        entities={},
        profile=profile,
    )
    assert snippets
