"""Regression tests for exact course-number wiki retrieval."""

from __future__ import annotations

import pytest

from app.retrieval.hybrid_wiki_retriever import retrieve_wiki_context_with_profile
from app.retrieval.obsidian_wiki_indexer import reset_wiki_index_cache
from app.retrieval.profiles import get_profile, reset_profile_config_cache


SAMPLE_PAGE = """---
title: Test Degree
track_slug: track-test
catalog_year: 2025
---

# Overview
General overview text.

## Requirements
Students must complete course 00940139 and electives.

## Electives
Choose from approved elective pool. See [[Electives]] for details.
"""


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "test-degree.md").write_text(SAMPLE_PAGE, encoding="utf-8")
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(wiki))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()
    yield wiki
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()


@pytest.mark.asyncio
async def test_exact_course_number_retrieval(wiki_dir):
    profile = get_profile("course_exact_lookup")
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="00940139 prerequisites",
        user_context={"profile": {"track": "track-test", "catalogYear": 2025}},
        entities={"courseNumber": "00940139"},
        profile=profile,
    )
    assert snippets
    assert any("00940139" in str(snippet.get("content") or "") for snippet in snippets)
    assert metadata["profileName"] == "course_exact_lookup"


@pytest.mark.asyncio
async def test_reranker_preserves_exact_matches(wiki_dir):
    profile = get_profile("course_exact_lookup")
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="00940139",
        user_context={"profile": {"catalogYear": 2025}},
        entities={"courseNumber": "00940139"},
        profile=profile,
    )
    assert metadata.get("topScore", 0) > 0
    assert "wiki:course:00940139" in metadata.get("sourceIds", [])


@pytest.mark.asyncio
async def test_no_result_for_unknown_course(wiki_dir):
    profile = get_profile("course_exact_lookup")
    snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="00000000 requirements",
        user_context={},
        entities={"courseNumber": "00000000"},
        profile=profile,
    )
    assert metadata["retrievedCount"] == 0 or snippets == []


@pytest.mark.asyncio
async def test_primary_course_page_wins_over_mentioned_prereq(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "courses" / "009-dds").mkdir(parents=True)
    (wiki / "courses" / "009-dds" / "00940202-intro-data.md").write_text(
        """---
title: "00940202 — Intro to Data"
course_code: "00940202"
---
# 00940202
## Description
Prerequisites include course 00140004 and 00140146 for DDS students in this long section.
""",
        encoding="utf-8",
    )
    (wiki / "other-degree.md").write_text(
        """---
title: Other Degree
track_slug: track-data-information-engineering
catalog_year: 2025
---
# Overview
Course 00140004 appears here with enough text for chunk indexing in unrelated degree pages.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(wiki))
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()
    profile = get_profile("course_exact_lookup")
    _snippets, _records, metadata = await retrieve_wiki_context_with_profile(
        query="Tell me about course 00940202",
        user_context={
            "profile": {
                "track": "track-data-information-engineering",
                "catalogYear": 2025,
                "degreeProgram": "DDS",
            }
        },
        entities={"courseNumber": "00940202"},
        profile=profile,
    )
    assert metadata.get("sourceIds")
    assert metadata["sourceIds"][0] == "wiki:course:00940202"
