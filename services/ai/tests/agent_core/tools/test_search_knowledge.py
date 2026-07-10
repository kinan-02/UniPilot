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
        assert set(match.keys()) == {"slug", "title", "titleHe", "kind", "sectionTitle", "content", "score"}
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


async def test_limit_is_clamped_to_hard_ceiling(use_real_academic_engine, monkeypatch):
    captured: dict[str, int] = {}
    original = use_real_academic_engine.search_wiki

    def _spy(query, limit=3, **kwargs):
        captured["limit"] = limit
        return original(query, limit=limit, **kwargs)

    monkeypatch.setattr(use_real_academic_engine, "search_wiki", _spy)
    await run_search_knowledge(SearchKnowledgeInput(query="student rights", limit=999))
    assert captured["limit"] == 20
