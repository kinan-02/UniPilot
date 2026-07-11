"""Unit tests for `get_track_requirements` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data fact verified directly before writing assertions: `get_entity`
for entity_type="track" never populates `warnings` (only the course path
does), so `track_result.warnings` is always `[]` in practice -- covered
implicitly by the success-path assertion below rather than as a separate
case.

- track-materials-engineering has 57 required courses (graph "contains"
  edges), including "01040019".
"""

from __future__ import annotations

from app.agent_core.tools.composites.get_track_requirements import (
    GetTrackRequirementsInput,
    run_get_track_requirements,
)


async def test_empty_track_slug_fails_closed():
    result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug="  "))
    assert result.ok is False
    assert "track_slug_required" in result.error


async def test_unknown_track_fails_closed(use_real_academic_engine):
    result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug="track-does-not-exist"))
    assert result.ok is False
    assert "track_not_found: track-does-not-exist" in result.error


async def test_successful_track_requirements(use_real_academic_engine):
    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-materials-engineering")
    )
    assert result.ok is True
    assert result.data["trackSlug"] == "track-materials-engineering"
    assert result.data["track"]["slug"] == "track-materials-engineering"
    assert len(result.data["requiredCourses"]) == 57
    required_ids = {entry["id"] for entry in result.data["requiredCourses"]}
    assert "01040019" in required_ids
    assert all(entry["nodeType"] == "course" for entry in result.data["requiredCourses"])
    assert result.warnings == []


async def test_required_courses_unavailable_degrades_gracefully(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.get_track_requirements as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_traverse(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="relation_unavailable")

    monkeypatch.setattr(module, "run_traverse_relationship", _fake_traverse)

    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-materials-engineering")
    )
    assert result.ok is True
    assert result.data["requiredCourses"] == []
    assert "required_courses_unavailable" in result.warnings
