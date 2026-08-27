"""Unit tests for `AcademicGraphEngine.retrieve_page_chunks` -- the page-scoped
section retrieval `interpret_text` reads instead of the whole page."""
from __future__ import annotations


async def test_scoped_retrieval_is_confined_to_the_named_page(use_real_academic_engine):
    engine = use_real_academic_engine
    sections = engine.retrieve_page_chunks("student-rights", "How long to appeal a grade?", limit=3)
    assert sections, "scoped retrieval returned nothing for a real page"
    assert all(s["slug"] == "student-rights" for s in sections), "leaked chunks from another page"


async def test_scoped_retrieval_narrows_below_the_whole_page(use_real_academic_engine):
    engine = use_real_academic_engine
    whole = engine.wiki_pages.get("student-rights", {}).get("content") or ""
    sections = engine.retrieve_page_chunks("student-rights", "How long to appeal a grade?", limit=3)
    joined = "\n\n".join(s["content"] for s in sections)
    assert 0 < len(joined) < len(whole), "scoped content should be non-empty and smaller than the whole page"


async def test_unknown_slug_returns_empty_so_caller_falls_back(use_real_academic_engine):
    engine = use_real_academic_engine
    assert engine.retrieve_page_chunks("no-such-page-slug", "anything", limit=3) == []


async def test_blank_query_returns_empty(use_real_academic_engine):
    engine = use_real_academic_engine
    assert engine.retrieve_page_chunks("student-rights", "   ", limit=3) == []
