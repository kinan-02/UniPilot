"""Unit tests for `traverse_relationship` (docs/agent/AGENT_VISION.md §5, primitive 3).

Every case runs against the real wiki + semester-catalog graph
(`use_real_academic_engine`), using edges verified to exist in that data:
- "00440148" --has_prerequisite--> "00440105", "00440140" (reused from
  `tests/test_academic_graph_engine.py`'s own eligibility case)
- "02140093" --belongs_to--> "track-education-biology" (course page wikilinks
  a track page under "Required in:")
- "track-materials-engineering" --contains--> "01040019" (track page's
  course table wikilinks a course page)
"""

from __future__ import annotations

from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)


async def test_empty_entity_fails_closed():
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="  ", relation="has_prerequisite")
    )
    assert result.ok is False
    assert "entity_required" in result.error


async def test_unknown_relation_fails_closed():
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="not_a_real_relation")
    )
    assert result.ok is False
    assert "unknown_relation" in result.error


async def test_unknown_entity_fails_closed(use_real_academic_engine):
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="99999999", relation="has_prerequisite")
    )
    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_prerequisites_forward(use_real_academic_engine):
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="has_prerequisite", direction="forward")
    )
    assert result.ok is True
    related = {entry["id"]: entry["nodeType"] for entry in result.data["relatedEntities"]}
    assert {"00440105", "00440140"} <= set(related)
    assert related["00440105"] == "course"
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_dependents_backward(use_real_academic_engine):
    """direction='backward' on has_prerequisite -- "what does this course
    block" -- the reverse-dependency need from the fail-course-X worked
    example (AGENT_VISION.md §10)."""
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440105", relation="has_prerequisite", direction="backward")
    )
    assert result.ok is True
    related_ids = {entry["id"] for entry in result.data["relatedEntities"]}
    assert "00440148" in related_ids


async def test_belongs_to_forward(use_real_academic_engine):
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="02140093", relation="belongs_to", direction="forward")
    )
    assert result.ok is True
    related_ids = {entry["id"] for entry in result.data["relatedEntities"]}
    assert "track-education-biology" in related_ids


async def test_contains_forward(use_real_academic_engine):
    result = await run_traverse_relationship(
        TraverseRelationshipInput(
            entity="track-materials-engineering", relation="contains", direction="forward"
        )
    )
    assert result.ok is True
    related_ids = {entry["id"] for entry in result.data["relatedEntities"]}
    assert "01040019" in related_ids


async def test_no_matches_returns_ok_with_empty_list(use_real_academic_engine):
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="contains", direction="forward")
    )
    assert result.ok is True
    assert result.data["relatedEntities"] == []


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="has_prerequisite")
    )
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_academic_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="has_prerequisite")
    )
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


async def test_backward_direction_with_no_matches(use_real_academic_engine):
    """Covers the `direction != "forward"` branch's empty-result path (the
    forward equivalent is `test_no_matches_returns_ok_with_empty_list`
    above) -- a course with no dependents under `has_prerequisite`."""
    result = await run_traverse_relationship(
        TraverseRelationshipInput(entity="00440148", relation="belongs_to", direction="backward")
    )
    assert result.ok is True
    assert result.data["relatedEntities"] == []
