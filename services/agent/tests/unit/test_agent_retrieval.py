"""Unit tests for wiki chunking and reranking."""

from app.retrieval.obsidian_wiki_indexer import chunk_wiki_page, reset_wiki_index_cache
from app.retrieval.reranker import rerank_chunks


SAMPLE_PAGE = """---
title: Test Degree
track_slug: track-test
catalog_year: 2025
---

# Overview
General overview text.

## Requirements
Students must complete course 00940139 and electives. See [[Electives]] for details.

## Electives
Choose from approved elective pool. See [[Electives]] for details.
"""


def setup_function() -> None:
    reset_wiki_index_cache()


def test_chunk_wiki_page_splits_sections():
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    assert len(chunks) >= 1
    assert any("00940139" in chunk.course_numbers_mentioned for chunk in chunks)
    assert any(chunk.section_title == "Requirements" for chunk in chunks)


def test_rerank_chunks_prefers_matching_section():
    chunks = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    ranked = rerank_chunks(chunks, query="00940139 prerequisites", limit=2)
    assert ranked
    assert ranked[0][1] > 0


def test_link_expansion_finds_linked_page():
    from app.retrieval.profiles import get_profile
    from app.retrieval.reranker import expand_linked_chunks, rerank_chunks

    page = chunk_wiki_page(relative_path="test/degree.md", text=SAMPLE_PAGE)
    elective_page = chunk_wiki_page(
        relative_path="test/electives.md",
        text="""---
title: Electives
track_slug: track-test
---

# Electives
Approved elective pool details for DDS students including credit limits and approval rules.
""",
    )
    chunks = [*page, *elective_page]
    profile = get_profile("requirement_explanation")
    ranked = rerank_chunks(chunks, query="requirements electives", limit=2, profile=profile)
    expanded = expand_linked_chunks(
        ranked,
        all_chunks=chunks,
        depth=1,
        max_linked=2,
        query="requirements electives",
        profile=profile,
    )
    assert len(expanded) >= len(ranked)
    titles = {chunk.page_title for chunk, _ in expanded}
    assert "Electives" in titles
