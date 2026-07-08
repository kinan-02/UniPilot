"""Additional RAG regression tests (Agent_RAG_tuning.md §28)."""

from __future__ import annotations

import pytest

from app.retrieval.hybrid_wiki_retriever import retrieve_wiki_context_with_profile
from app.retrieval.metadata_filter import filter_wiki_chunks
from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page, reset_wiki_index_cache
from app.retrieval.profiles import get_profile, reset_profile_config_cache
from app.retrieval.reranker import expand_linked_chunks, rerank_chunks


DEGREE_PAGE = """---
title: Test Degree
track_slug: track-test
catalog_year: 2025
---

# Overview
General overview text for the DDS track requirements document.

## Requirements
Students must complete course 00940139 and electives. See [[Electives]] for details.

## דרישות
יש להשלים קורס 00940139 וקורסי בחירה מאושרים.
"""


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    track_dir = wiki / "entities" / "tracks"
    track_dir.mkdir(parents=True)
    (track_dir / "track-test.md").write_text(DEGREE_PAGE, encoding="utf-8")
    (wiki / "electives.md").write_text(
        """---
title: Electives
track_slug: track-test
---

# Electives
Approved elective pool details for DDS students including credit limits and approval rules.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACADEMIC_WIKI_PATH", str(wiki))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()
    yield wiki
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()


@pytest.mark.asyncio
async def test_mixed_language_query(wiki_dir):
    profile = get_profile("requirement_explanation")
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="דרישות תואר DDS requirements",
        user_context={"profile": {"track": "track-test", "catalogYear": 2025}},
        entities={},
        profile=profile,
    )
    assert snippets
    assert metadata["retrievedCount"] >= 1


@pytest.mark.asyncio
async def test_metadata_relaxation_fallback(wiki_dir):
    profile = get_profile("requirement_explanation")
    snippets_strict, _, meta_strict = await retrieve_wiki_context_with_profile(
        query="requirements electives",
        user_context={"profile": {"track": "nonexistent-track", "catalogYear": 2099}},
        entities={},
        profile=profile,
    )
    assert snippets_strict == [] or meta_strict.get("fallbackUsed") is True


def test_link_expansion_does_not_add_noise():
    profile = get_profile("requirement_explanation")
    degree_chunks = chunk_wiki_page(relative_path="test/degree.md", text=DEGREE_PAGE)
    noise_chunks = chunk_wiki_page(
        relative_path="test/unrelated.md",
        text="""---
title: Unrelated Sports Club
---

# Unrelated Sports Club
This page discusses basketball schedules and has nothing to do with academics.
""",
    )
    elective_chunks = chunk_wiki_page(
        relative_path="test/electives.md",
        text="""---
title: Electives
---

# Electives
Approved elective pool details for DDS students including credit limits and approval rules.
""",
    )
    all_chunks = [*degree_chunks, *noise_chunks, *elective_chunks]
    ranked = rerank_chunks(
        degree_chunks,
        query="requirements electives",
        limit=2,
        profile=profile,
    )
    expanded = expand_linked_chunks(
        ranked,
        all_chunks=all_chunks,
        depth=1,
        max_linked=2,
        query="requirements electives",
        profile=profile,
    )
    titles = {chunk.page_title for chunk, _ in expanded}
    assert "Unrelated Sports Club" not in titles
    assert "Electives" in titles


def test_course_filter_returns_empty_when_no_match():
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=DEGREE_PAGE)
    filtered = filter_wiki_chunks(chunks, course_number="00000000")
    assert filtered == []
