"""Unit tests for `search_knowledge` (docs/agent/AGENT_VISION.md §5, primitive 2).

Real-data cases run against the real wiki via `use_real_academic_engine`.
Query/behavior facts below were verified directly against
`AcademicGraphEngine.search_wiki` before writing assertions, not assumed:
- "student rights ombudsman" ranks the "student-rights" page/chunks highly.
- "a b c" tokenizes to nothing (`_tokenize_search` drops tokens shorter than
  2 chars), so `search_wiki` returns `[]` via its own early-exit -- a clean,
  deterministic way to exercise the zero-matches path without depending on
  corpus content.
- No `EMBEDDING_API_KEY` is configured in this environment (no `.env`,
  `embedding_api_key` defaults to `None`), so every real-data case here
  exercises the deterministic BM25-only fallback -- no live network calls.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import ValidationError

from app.agent_core.tools.primitives.search_knowledge import SearchKnowledgeInput, run_search_knowledge


async def test_empty_query_fails_closed():
    result = await run_search_knowledge(SearchKnowledgeInput(query="   "))
    assert result.ok is False
    assert result.data is None
    assert "query_required" in result.error


def test_limit_below_one_rejected_by_schema():
    with pytest.raises(ValidationError):
        SearchKnowledgeInput(query="anything", limit=0)


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights"))
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_academic_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights"))
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


async def test_search_wiki_exception_fails_closed(use_real_academic_engine, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(use_real_academic_engine, "search_wiki", _raise)
    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights"))
    assert result.ok is False
    assert "search_failed" in result.error


async def test_search_returns_ranked_matches(use_real_academic_engine):
    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights ombudsman"))
    assert result.ok is True
    assert result.data["query"] == "student rights ombudsman"
    matches = result.data["matches"]
    assert matches
    assert any(match["slug"] == "student-rights" for match in matches)
    for match in matches:
        assert set(match.keys()) == {"slug", "title", "titleHe", "kind", "courseCode", "sectionTitle", "content", "score"}
    assert result.certainty.basis == "wiki_derived"
    assert 0.0 <= result.certainty.confidence <= 1.0
    assert result.certainty.source_ref is not None
    assert result.certainty.source_ref.page == matches[0]["slug"]


async def test_no_matches_is_ok_true_with_empty_list(use_real_academic_engine):
    """"a b c" tokenizes to nothing -- verified directly against
    `AcademicGraphEngine._tokenize_search` -- so this deterministically
    exercises the zero-matches path regardless of corpus content."""
    result = await run_search_knowledge(SearchKnowledgeInput(query="a b c"))
    assert result.ok is True
    assert result.error is None
    assert result.data["matches"] == []
    assert result.certainty.confidence == 0.0
    assert result.certainty.source_ref is None


async def test_limit_is_respected(use_real_academic_engine):
    result = await run_search_knowledge(SearchKnowledgeInput(query="course prerequisites credits", limit=2))
    assert result.ok is True
    assert len(result.data["matches"]) <= 2


async def test_non_course_kind_hit_has_none_course_code(use_real_academic_engine):
    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights ombudsman"))
    match = next(m for m in result.data["matches"] if m["slug"] == "student-rights")
    assert match["kind"] != "course"
    assert match["courseCode"] is None


async def test_course_kind_hit_resolves_course_code_from_the_real_engine_map(use_real_academic_engine, monkeypatch):
    """00440148's wiki page (slug `00440148-waves-distributed-systems`) is the
    same real, verified course fixture `test_get_entity.py` uses -- proves
    `courseCode` resolves via the real engine's `slug_to_course_code` map,
    not a canned/fabricated value."""
    real_search_wiki = use_real_academic_engine.search_wiki

    def _inject_course_hit(query, **kwargs):
        hits = real_search_wiki(query, **kwargs)
        hits.insert(
            0,
            {
                "slug": "00440148-waves-distributed-systems",
                "title": "Waves and Distributed Systems",
                "title_he": None,
                "kind": "course",
                "sectionTitle": None,
                "content": "...",
                "score": 5.0,
            },
        )
        return hits

    monkeypatch.setattr(use_real_academic_engine, "search_wiki", _inject_course_hit)

    result = await run_search_knowledge(SearchKnowledgeInput(query="student rights"))
    course_match = next(m for m in result.data["matches"] if m["slug"] == "00440148-waves-distributed-systems")
    assert course_match["courseCode"] == "00440148"


async def test_limit_is_clamped_to_hard_ceiling(use_real_academic_engine, monkeypatch):
    captured: dict[str, int] = {}
    original = use_real_academic_engine.search_wiki

    def _spy(query, limit=3, **kwargs):
        captured["limit"] = limit
        return original(query, limit=limit, **kwargs)

    monkeypatch.setattr(use_real_academic_engine, "search_wiki", _spy)
    await run_search_knowledge(SearchKnowledgeInput(query="student rights", limit=999))
    assert captured["limit"] == 20


async def test_search_wiki_does_not_block_the_event_loop(use_real_academic_engine, monkeypatch):
    """`search_wiki` (BM25 + optional embeddings) is fully synchronous --
    called directly rather than via `asyncio.to_thread`, a slow/blocking
    call inside it would freeze the entire event loop, not just this one
    coroutine. Found live: once embeddings were configured, a turn's own
    300s `asyncio.wait_for` only fired at 463s, because a blocking call
    never yields control back for the timeout to be observed. Proven here
    by running a deliberately slow (blocking `time.sleep`, not
    `asyncio.sleep`) `search_wiki` concurrently with a lightweight
    coroutine that must still complete promptly if the slow call is
    correctly off-loaded to a separate thread.
    """

    def _slow_blocking_search(*_args, **_kwargs):
        time.sleep(0.3)
        return []

    monkeypatch.setattr(use_real_academic_engine, "search_wiki", _slow_blocking_search)

    ticks: list[float] = []

    async def _tick_every_50ms():
        for _ in range(4):
            await asyncio.sleep(0.05)
            ticks.append(time.monotonic())

    start = time.monotonic()
    await asyncio.gather(
        run_search_knowledge(SearchKnowledgeInput(query="student rights")),
        _tick_every_50ms(),
    )

    # If search_wiki blocked the event loop, every tick would be delayed
    # until after the 0.3s blocking call finished, landing all 4 ticks
    # bunched up near the very end instead of spread every ~50ms.
    assert len(ticks) == 4
    assert ticks[0] - start < 0.2

